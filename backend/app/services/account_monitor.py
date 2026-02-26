"""
账户监控服务 - 定期推送账户余额和持仓数据，并定时保存净值快照
"""
import asyncio
from loguru import logger
from datetime import datetime
from app.websocket.manager import broadcast_balance_update, broadcast_positions_update
from app.services.api_config_service import api_config_service


def safe_float(value, default=0.0):
    """安全地将值转换为浮点数"""
    if not value:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class AccountMonitor:
    """账户监控器 - 定期推送账户数据并保存净值快照"""

    def __init__(self, interval: int = 10):
        """
        初始化账户监控器

        Args:
            interval: 推送间隔(秒),默认10秒
        """
        self.interval = interval
        self.is_running = False
        self._task = None
        # 快照计数器：每360次循环(= 3600秒 = 1小时)保存一次快照
        self._snapshot_counter = 0
        self._snapshot_interval = 360

    async def start(self):
        """启动监控"""
        if self.is_running:
            logger.warning("账户监控器已在运行")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"✅ 账户监控器已启动 (推送间隔: {self.interval}秒, 快照间隔: {self._snapshot_interval * self.interval}秒)")

    async def stop(self):
        """停止监控"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("账户监控器已停止")

    async def _monitor_loop(self):
        """监控循环"""
        first_run = True
        while self.is_running:
            try:
                # 推送余额更新，同时获取用于快照的数据
                snapshot_data = await self._push_balance_update()

                # 推送持仓更新
                await self._push_positions_update()

                # 首次运行立即保存快照，之后每小时一次
                self._snapshot_counter += 1
                if first_run or self._snapshot_counter >= self._snapshot_interval:
                    self._snapshot_counter = 0
                    first_run = False
                    if snapshot_data:
                        await self._save_snapshot(snapshot_data)

                # 等待下一次推送
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"账户监控循环出错: {e}")
                await asyncio.sleep(self.interval)

    async def _push_balance_update(self) -> dict | None:
        """推送余额更新，返回用于快照的核心数据"""
        try:
            # 获取用户的交易所实例
            exchange = api_config_service.get_exchange(user_id=1)
            if not exchange:
                return None

            # 获取账户余额
            balance_data = await exchange.get_balance()

            if balance_data:
                # 构造WebSocket推送数据
                total_eq = safe_float(balance_data.get("totalEq"))
                imr = safe_float(balance_data.get("imr"))  # 占用保证金

                # 计算可用余额(从details中累加)
                available_balance = 0.0
                total_upl = 0.0
                details = balance_data.get("details", [])

                for detail in details:
                    available_balance += safe_float(detail.get("availBal"))
                    # 累加各币种的未实现盈亏
                    upl = safe_float(detail.get("upl"))
                    iso_upl = safe_float(detail.get("isoUpl"))
                    total_upl += (upl + iso_upl)

                ws_data = {
                    "total_equity": total_eq,
                    "available_balance": available_balance,
                    "unrealized_pnl": total_upl,
                    "margin_ratio": safe_float(balance_data.get("mgnRatio")),
                    "imr": imr,
                    "details": details,
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }

                # 广播余额更新
                await broadcast_balance_update(ws_data)
                logger.debug(f"余额更新已推送: 总权益={total_eq}, 未实现盈亏={total_upl}")

                # 返回用于快照的核心数据
                return {
                    "total_equity": total_eq,
                    "available_balance": available_balance,
                    "unrealized_pnl": total_upl,
                }

        except Exception as e:
            logger.error(f"推送余额更新失败: {e}")

        return None

    async def _push_positions_update(self):
        """推送持仓更新"""
        try:
            # 获取用户的交易所实例
            exchange = api_config_service.get_exchange(user_id=1)
            if not exchange:
                return

            # 获取所有持仓
            positions = await exchange.get_positions(inst_type="SWAP")

            if positions is not None:
                # 过滤掉空持仓
                active_positions = []
                total_unrealized_pnl = 0.0

                for pos in positions:
                    pos_size = safe_float(pos.get("pos"))
                    if pos_size != 0:  # 只推送有持仓的
                        upl = safe_float(pos.get("upl"))
                        total_unrealized_pnl += upl

                        active_positions.append({
                            "symbol": pos.get("instId", ""),
                            "side": "long" if pos_size > 0 else "short",
                            "size": abs(pos_size),
                            "avg_price": safe_float(pos.get("avgPx")),
                            "current_price": safe_float(pos.get("markPx")),
                            "unrealized_pnl": upl,
                            "unrealized_pnl_pct": safe_float(pos.get("uplRatio")) * 100,
                            "margin": safe_float(pos.get("margin")),
                            "liquidation_price": safe_float(pos.get("liqPx")) if pos.get("liqPx") else None,
                            "leverage": safe_float(pos.get("lever")),
                            "inst_type": pos.get("instType", "SWAP"),
                            "notional_usd": safe_float(pos.get("notionalUsd")),  # OKX返回的持仓美元价值
                        })

                # 构造WebSocket推送数据
                ws_data = {
                    "positions": active_positions,
                    "total_positions": len(active_positions),
                    "total_unrealized_pnl": total_unrealized_pnl,
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }

                # 广播持仓更新
                await broadcast_positions_update(ws_data)

        except Exception as e:
            logger.error(f"推送持仓更新失败: {e}")

    async def _save_snapshot(self, data: dict):
        """保存账户净值快照到数据库（每小时一次）"""
        def _sync_save():
            from app.core.database import SessionLocal
            from app.models.account_snapshot import AccountSnapshot
            db = SessionLocal()
            try:
                snapshot = AccountSnapshot(
                    user_id=1,
                    total_equity=data["total_equity"],
                    available_balance=data.get("available_balance", 0.0),
                    unrealized_pnl=data.get("unrealized_pnl", 0.0),
                )
                db.add(snapshot)
                db.commit()
                logger.info(f"账户净值快照已保存: equity={data['total_equity']:.2f}")
            except Exception as e:
                db.rollback()
                logger.error(f"保存账户净值快照失败: {e}")
            finally:
                db.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_save)


# 全局实例
account_monitor = AccountMonitor(interval=10)  # 每10秒推送一次
