"""
账户监控服务 - 定期推送账户余额和持仓数据，并定时保存净值快照
"""
import asyncio
from loguru import logger
from datetime import datetime
from typing import Optional
from app.websocket.manager import broadcast_balance_update, broadcast_positions_update
from app.services.api_config_service import api_config_service
from app.services.exchange.okx import OKXExchange
from app.services.notification.notification_service import notification_service


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
        # 复用同一个 exchange 实例，避免每次创建新 session 造成资源泄漏
        self._exchange = None
        # 快照计数器：每360次循环(= 3600秒 = 1小时)保存一次快照
        self._snapshot_counter = 0
        self._snapshot_interval = 360
        self.user_id = 1
        self._last_daily_report_date = None

    def _get_exchange(self):
        """获取或创建 exchange 实例（复用，不重复创建）"""
        if self._exchange is None:
            config = api_config_service.get_active_config(self.user_id)
            if not config or not config.is_valid:
                return None
            self._exchange = OKXExchange(
                api_key=config.api_key,
                secret_key=config.secret_key,
                passphrase=config.passphrase,
                simulated=config.is_simulated,
                proxy=config.proxy,
            )
        return self._exchange

    async def start(self):
        """启动监控"""
        if self.is_running:
            logger.warning("账户监控器已在运行")
            return

        # 账户监控只使用系统内已激活配置，不回退 .env，避免无效开发 key 持续刷 OKX 私有接口。
        self._exchange = self._get_exchange()
        if self._exchange is None:
            logger.warning("未找到有效且激活的系统内API配置，账户监控器不启动")
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
        # 关闭 exchange session，释放 aiohttp 连接
        if self._exchange is not None:
            try:
                await self._exchange.close()
            except Exception:
                pass
            self._exchange = None
        logger.info("账户监控器已停止")

    async def _monitor_loop(self):
        """监控循环"""
        first_run = True
        while self.is_running:
            try:
                # 推送余额更新，同时获取用于快照的数据
                snapshot_data = await self._push_balance_update()

                # 推送持仓更新
                positions_data = await self._push_positions_update()

                # 首次运行立即保存快照，之后每小时一次
                self._snapshot_counter += 1
                if first_run or self._snapshot_counter >= self._snapshot_interval:
                    self._snapshot_counter = 0
                    first_run = False
                    if snapshot_data:
                        await self._save_snapshot(snapshot_data)

                await self._maybe_send_daily_report(snapshot_data, positions_data)

                # 等待下一次推送
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"账户监控循环出错: {e}")
                await asyncio.sleep(self.interval)

    async def _push_balance_update(self) -> Optional[dict]:
        """推送余额更新，返回用于快照的核心数据"""
        try:
            exchange = self._get_exchange()
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
                    "adjusted_equity": safe_float(balance_data.get("adjEq")),
                    "imr": imr,
                    "mmr": safe_float(balance_data.get("mmr")),
                    "notional_usd": safe_float(balance_data.get("notionalUsd")),
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

    async def _push_positions_update(self) -> Optional[dict]:
        """推送持仓更新"""
        try:
            exchange = self._get_exchange()
            if not exchange:
                return None

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
                        pos_side = pos.get("posSide") or "net"
                        side = pos_side if pos_side in ("long", "short") else ("long" if pos_size > 0 else "short")
                        total_unrealized_pnl += upl

                        active_positions.append({
                            "pos_id": pos.get("posId", ""),
                            "pos_side": pos_side,
                            "mgn_mode": pos.get("mgnMode", ""),
                            "symbol": pos.get("instId", ""),
                            "side": side,
                            "size": abs(pos_size),
                            "avg_price": safe_float(pos.get("avgPx")),
                            "current_price": safe_float(pos.get("markPx")),
                            "last_price": safe_float(pos.get("last")),
                            "unrealized_pnl": upl,
                            "unrealized_pnl_pct": safe_float(pos.get("uplRatio")) * 100,
                            "margin": safe_float(pos.get("margin")),
                            "imr": safe_float(pos.get("imr")),
                            "mmr": safe_float(pos.get("mmr")),
                            "mgn_ratio": safe_float(pos.get("mgnRatio")),
                            "adl": safe_float(pos.get("adl")),
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
                return ws_data

        except Exception as e:
            logger.error(f"推送持仓更新失败: {e}")
        return None

    async def _save_snapshot(self, data: dict):
        """保存账户净值快照到数据库（每小时一次）"""
        def _sync_save():
            from app.core.database import SessionLocal
            from app.models.account_snapshot import AccountSnapshot
            db = SessionLocal()
            try:
                new_equity = data["total_equity"]

                # 校验：equity <= 0 直接跳过，不保存
                if new_equity <= 0:
                    logger.warning(f"快照 equity={new_equity:.2f} 异常，跳过保存")
                    return

                # 校验：与最近一次快照对比，变化超过 80% 视为异常数据，跳过
                last = (
                    db.query(AccountSnapshot)
                    .filter(AccountSnapshot.user_id == 1)
                    .order_by(AccountSnapshot.created_at.desc())
                    .first()
                )
                if last and last.total_equity > 0:
                    change_pct = abs(new_equity - last.total_equity) / last.total_equity
                    if change_pct > 0.8:
                        logger.warning(
                            f"快照 equity 波动异常 ({last.total_equity:.2f} → {new_equity:.2f}"
                            f"，变化 {change_pct*100:.1f}%)，跳过保存"
                        )
                        return

                snapshot = AccountSnapshot(
                    user_id=1,
                    total_equity=new_equity,
                    available_balance=data.get("available_balance", 0.0),
                    unrealized_pnl=data.get("unrealized_pnl", 0.0),
                )
                db.add(snapshot)
                db.commit()
                logger.info(f"账户净值快照已保存: equity={new_equity:.2f}")
            except Exception as e:
                db.rollback()
                logger.error(f"保存账户净值快照失败: {e}")
            finally:
                db.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_save)

    async def _maybe_send_daily_report(self, balance_data: Optional[dict], positions_data: Optional[dict]):
        """每天晚间发送一次账户摘要。"""
        now = datetime.now()
        if now.hour < 23 or (now.hour == 23 and now.minute < 50):
            return
        if self._last_daily_report_date == now.date():
            return
        if not balance_data:
            return

        positions = (positions_data or {}).get("positions", [])
        total_unrealized_pnl = safe_float((positions_data or {}).get("total_unrealized_pnl"))
        position_lines = []
        for pos in positions[:5]:
            position_lines.append(
                f"{pos.get('symbol')} {pos.get('side')} "
                f"upl={safe_float(pos.get('unrealized_pnl')):.2f} "
                f"notional={safe_float(pos.get('notional_usd')):.2f}"
            )

        try:
            await notification_service.send_strategy_notification(
                strategy_id=0,
                title="账户日报",
                message=(
                    f"总权益 {safe_float(balance_data.get('total_equity')):.2f} USDT，"
                    f"可用 {safe_float(balance_data.get('available_balance')):.2f} USDT，"
                    f"持仓 {len(positions)} 个，未实现盈亏 {total_unrealized_pnl:.2f} USDT"
                ),
                level="info",
                data={
                    "total_equity": round(safe_float(balance_data.get("total_equity")), 4),
                    "available_balance": round(safe_float(balance_data.get("available_balance")), 4),
                    "unrealized_pnl": round(total_unrealized_pnl, 4),
                    "positions": position_lines,
                },
            )
            self._last_daily_report_date = now.date()
        except Exception as exc:
            logger.error(f"发送账户日报失败: {exc}")


# 全局实例
account_monitor = AccountMonitor(interval=10)  # 每10秒推送一次
