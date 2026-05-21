"""
策略管理器 - 管理所有运行中的策略实例
"""
from typing import Dict, Optional
from loguru import logger
from .base import StrategyBase
from app.services.exchange.okx import OKXExchange
from app.models.strategy import StrategyType, Strategy, StrategyEvent, StrategyStatus
from app.core.database import SessionLocal
from app.websocket.manager import broadcast_strategy_stats, broadcast_strategy_update, broadcast_notification
import asyncio
from datetime import datetime
import inspect
import math
import time


class StrategyManager:
    """策略管理器 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 运行中的策略实例 {strategy_id: strategy_instance}
        self.strategies: Dict[int, StrategyBase] = {}

        # 策略监控任务 {strategy_id: asyncio.Task}
        self.strategy_tasks: Dict[int, asyncio.Task] = {}

        # 交易所实例缓存 {symbol: exchange_instance}
        self.exchanges: Dict[str, OKXExchange] = {}

        self._initialized = True
        logger.info("策略管理器初始化完成")

    def get_exchange(self, api_key: str, secret_key: str, passphrase: str) -> OKXExchange:
        """获取或创建交易所实例"""
        # 使用API key作为缓存键
        cache_key = api_key

        if cache_key not in self.exchanges:
            self.exchanges[cache_key] = OKXExchange(
                api_key=api_key,
                secret_key=secret_key,
                passphrase=passphrase
            )
            logger.info(f"创建新的交易所实例: {cache_key}")

        return self.exchanges[cache_key]

    def log_strategy_event(
        self,
        strategy_id: int,
        event_type: str,
        title: str,
        message: str = "",
        level: str = "info",
        data: Optional[dict] = None,
        parameter_snapshot: Optional[dict] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """写入策略运行事件。失败时只记 debug，不能影响交易主流程。"""
        db = SessionLocal()
        try:
            db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            resolved_user_id = user_id or (db_strategy.user_id if db_strategy else None)
            if resolved_user_id is None:
                return

            db.add(StrategyEvent(
                strategy_id=strategy_id,
                user_id=resolved_user_id,
                event_type=event_type,
                level=level,
                title=title,
                message=message,
                data=data or {},
                parameter_snapshot=parameter_snapshot,
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.debug(f"写入策略事件失败 strategy_id={strategy_id}: {exc}")
        finally:
            db.close()

    def create_strategy(
        self,
        strategy_id: int,
        strategy_type,  # 可以是 StrategyType 枚举或字符串
        symbol: str,
        parameters: dict,
        exchange: OKXExchange,
        user_id: int = 1
    ) -> StrategyBase:
        """创建策略实例"""

        # 将字符串类型转换为枚举（如果需要）
        if isinstance(strategy_type, str):
            try:
                strategy_type_enum = StrategyType(strategy_type.lower())
            except ValueError:
                raise ValueError(f"不支持的策略类型: {strategy_type}")
        else:
            strategy_type_enum = strategy_type

        if strategy_type_enum == StrategyType.ADAPTIVE_GRID_TREND:
            from app.services.strategy.adaptive_grid_trend import AdaptiveGridTrendStrategy
            return AdaptiveGridTrendStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id,
            )

        raise ValueError("后端当前仅支持自适应趋势网格策略")

    async def _persist_strategy_state(self, strategy_id: int, strategy: StrategyBase):
        """持久化策略状态到数据库"""
        db = SessionLocal()
        try:
            # 查询策略记录
            db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if not db_strategy:
                logger.warning(f"策略 {strategy_id} 不存在于数据库中")
                return

            # 从策略获取运行时数据（通用方法）
            realized = strategy.realized_pnl if hasattr(strategy, 'realized_pnl') else 0
            unrealized = getattr(strategy, '_unrealized_pnl', 0)
            db_strategy.total_profit = round(realized + unrealized, 4)  # 总盈亏 = 已实现 + 未实现
            db_strategy.total_trades = strategy.total_trades if hasattr(strategy, 'total_trades') else 0
            db_strategy.win_rate = strategy.win_rate if hasattr(strategy, 'win_rate') else 0

            # 持仓状态持久化（用于重启后恢复，防止重复开仓）
            position_side = getattr(strategy, '_position_side', None)
            if position_side is not None:
                # 新版双向持仓策略（TrendFollowStrategy）
                db_strategy.position_in_position   = position_side != ""
                db_strategy.position_side          = position_side
                db_strategy.position_entry_price   = getattr(strategy, '_entry_price', 0.0)
                db_strategy.position_qty           = getattr(strategy, '_position_qty', 0.0)
                db_strategy.position_open_time     = getattr(strategy, '_open_time', 0.0)
                db_strategy.position_highest_price = getattr(strategy, '_extreme_price',
                                                     getattr(strategy, '_highest_price', 0.0))
                db_strategy.position_trail_stop_px = getattr(strategy, '_trail_stop_px', 0.0)
            elif hasattr(strategy, '_in_position'):
                # 旧版单向持仓策略（向后兼容）
                db_strategy.position_in_position   = strategy._in_position
                db_strategy.position_side          = "long" if strategy._in_position else ""
                db_strategy.position_entry_price   = getattr(strategy, '_entry_price', 0.0)
                db_strategy.position_qty           = getattr(strategy, '_position_qty', 0.0)
                db_strategy.position_open_time     = getattr(strategy, '_open_time', 0.0)
                db_strategy.position_highest_price = getattr(strategy, '_highest_price', 0.0)
                db_strategy.position_trail_stop_px = getattr(strategy, '_trail_stop_px', 0.0)

            db.commit()

            logger.debug(
                f"策略 {strategy_id} 状态已更新: "
                f"盈亏={db_strategy.total_profit:.2f}, 交易数={db_strategy.total_trades}, 胜率={db_strategy.win_rate:.1f}%"
            )

            # 通过WebSocket广播策略状态更新
            try:
                await broadcast_strategy_update(strategy_id, {
                    "strategy_id": strategy_id,
                    "total_profit": db_strategy.total_profit,
                    "total_trades": db_strategy.total_trades,
                    "win_rate": db_strategy.win_rate,
                    "status": "running",
                    "timestamp": asyncio.get_event_loop().time()
                })
            except Exception as ws_err:
                logger.error(f"广播策略状态失败: {ws_err}")

        except Exception as e:
            db.rollback()
            logger.error(f"持久化策略 {strategy_id} 状态失败: {e}")
            raise
        finally:
            db.close()

    async def _pause_strategy_for_fuse(self, strategy_id: int, strategy: StrategyBase, reason: str):
        """运行期风控触发后暂停策略。"""
        logger.warning(f"策略 {strategy_id} 触发运行期风控熔断: {reason}")
        self.log_strategy_event(
            strategy_id=strategy_id,
            event_type="risk_pause",
            level="warning",
            title="策略触发风控暂停",
            message=reason,
            data={
                "symbol": strategy.symbol,
                "daily_realized_pnl": strategy.daily_realized_pnl,
                "max_runtime_drawdown": strategy.max_runtime_drawdown,
                "consecutive_losses": strategy.consecutive_losses,
                "recent_trade_pnl": strategy.trade_pnl_history[-10:],
            },
            parameter_snapshot=strategy.parameters if isinstance(strategy.parameters, dict) else None,
            user_id=strategy.user_id,
        )

        risk_fuse = strategy.parameters.get("risk_fuse", {}) if isinstance(strategy.parameters, dict) else {}
        if not isinstance(risk_fuse, dict):
            risk_fuse = {}
        close_position = bool(risk_fuse.get("close_position_on_trigger", False))
        cancel_orders = bool(risk_fuse.get("cancel_orders_on_trigger", True))

        try:
            stop_sig = inspect.signature(strategy.stop)
            kwargs = {}
            if 'cancel_orders' in stop_sig.parameters:
                kwargs['cancel_orders'] = cancel_orders
            if 'close_position' in stop_sig.parameters:
                kwargs['close_position'] = close_position
            await strategy.stop(**kwargs)
        except Exception as exc:
            logger.error(f"策略 {strategy_id} 熔断暂停时 stop() 失败: {exc}")
            strategy.is_running = False

        db = SessionLocal()
        try:
            db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if db_strategy:
                db_strategy.status = StrategyStatus.PAUSED
                db_strategy.stopped_at = datetime.now()
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"策略 {strategy_id} 熔断状态写入数据库失败: {exc}")
        finally:
            db.close()

        try:
            await broadcast_notification({
                "type": "warning",
                "title": "策略已自动暂停",
                "message": f"策略 {strategy.symbol} 触发运行期风控: {reason}",
                "strategy_id": strategy_id,
                "timestamp": time.time()
            })
            await broadcast_strategy_update(strategy_id, {
                "strategy_id": strategy_id,
                "status": StrategyStatus.PAUSED.value,
                "fuse_reason": reason,
                "timestamp": time.time()
            })
        except Exception as ws_err:
            logger.error(f"广播策略熔断状态失败: {ws_err}")

    def _check_runtime_fuse(self, strategy: StrategyBase) -> Optional[str]:
        """检查策略运行期风控熔断条件。"""
        if not isinstance(strategy.parameters, dict):
            return None

        risk_fuse = strategy.parameters.get("risk_fuse")
        if risk_fuse is None:
            risk_fuse = {}
        if not isinstance(risk_fuse, dict):
            return None
        if not risk_fuse.get("enabled", True):
            return None

        max_losses = int(risk_fuse.get("max_consecutive_losses", 3))
        if max_losses > 0 and strategy.consecutive_losses >= max_losses:
            return f"连续亏损 {strategy.consecutive_losses} 次，达到阈值 {max_losses} 次"

        max_position_usd = float(strategy.parameters.get("max_position_usd", 0) or 0)
        risk_base_usd = float(
            risk_fuse.get("risk_base_usd")
            or strategy.parameters.get("risk_base_usd")
            or strategy.parameters.get("initial_capital")
            or max(max_position_usd * 2, 1000)
        )

        daily_loss_pct = risk_fuse.get("daily_loss_limit_pct", 0.02)
        if daily_loss_pct is not None and risk_base_usd > 0:
            daily_limit = risk_base_usd * float(daily_loss_pct)
            if daily_limit > 0 and strategy.daily_realized_pnl <= -daily_limit:
                return (
                    f"当日已实现亏损 {strategy.daily_realized_pnl:.4f} USDT，"
                    f"达到日亏损上限 {daily_limit:.4f} USDT"
                )

        daily_loss_usd = risk_fuse.get("daily_loss_limit_usd")
        if daily_loss_usd is not None:
            daily_limit = float(daily_loss_usd)
            if daily_limit > 0 and strategy.daily_realized_pnl <= -daily_limit:
                return (
                    f"当日已实现亏损 {strategy.daily_realized_pnl:.4f} USDT，"
                    f"达到日亏损上限 {daily_limit:.4f} USDT"
                )

        max_drawdown_pct = risk_fuse.get("max_drawdown_pct", 0.05)
        if max_drawdown_pct is not None and risk_base_usd > 0:
            drawdown_limit = risk_base_usd * float(max_drawdown_pct)
            if drawdown_limit > 0 and strategy.max_runtime_drawdown >= drawdown_limit:
                return (
                    f"运行期回撤 {strategy.max_runtime_drawdown:.4f} USDT，"
                    f"达到回撤上限 {drawdown_limit:.4f} USDT"
                )

        pf_window = int(risk_fuse.get("profit_factor_window", 10))
        min_pf_trades = int(risk_fuse.get("min_trades_for_profit_factor", 8))
        min_profit_factor = float(risk_fuse.get("min_profit_factor", 0.8))
        recent_count = len(strategy.trade_pnl_history[-pf_window:]) if pf_window > 0 else len(strategy.trade_pnl_history)
        if min_profit_factor > 0 and recent_count >= min_pf_trades:
            profit_factor = strategy.runtime_profit_factor(pf_window)
            if profit_factor is not None and profit_factor < min_profit_factor:
                return (
                    f"最近 {recent_count} 笔盈亏比 {profit_factor:.2f}，"
                    f"低于阈值 {min_profit_factor:.2f}"
                )

        return None

    async def _run_strategy_loop(self, strategy_id: int, strategy: StrategyBase):
        """策略运行时监控循环"""
        logger.info(f"启动策略监控循环: strategy_id={strategy_id}")

        # 持久化计数器（每10次循环更新一次数据库，约50秒）
        persist_counter = 0

        try:
            while strategy.is_running:
                try:
                    # 1. 获取最新ticker并调用 on_tick
                    ticker = await strategy.exchange.get_ticker(strategy.symbol)
                    await strategy.on_tick(ticker)

                    fuse_reason = self._check_runtime_fuse(strategy)
                    if fuse_reason:
                        await self._pause_strategy_for_fuse(strategy_id, strategy, fuse_reason)
                        break

                    # 2. 定期持久化策略状态到数据库
                    persist_counter += 1
                    if persist_counter >= 10:  # 每10次循环（约50秒）更新一次
                        persist_counter = 0
                        try:
                            await self._persist_strategy_state(strategy_id, strategy)
                        except Exception as e:
                            logger.error(f"持久化策略状态失败: {e}")

                    # 3. 每次循环都广播策略实时统计（用于Dashboard实时更新）
                    try:
                        stats = self.get_strategy_stats(strategy_id)
                        if stats:
                            await broadcast_strategy_stats(strategy_id, stats)
                    except Exception as e:
                        logger.error(f"广播策略统计失败: {e}")

                    # 4. 等待一段时间再进行下一次循环（避免API请求过于频繁）
                    await asyncio.sleep(5)  # 每5秒检查一次

                except Exception as e:
                    logger.error(f"策略监控循环出错: {e}")

                    # 发送监控循环出错警告
                    try:
                        await broadcast_notification({
                            "type": "warning",
                            "title": "策略监控异常",
                            "message": f"策略 {strategy.symbol} 监控循环出现错误: {str(e)}",
                            "strategy_id": strategy_id,
                            "timestamp": time.time()
                        })
                    except Exception as notify_err:
                        logger.error(f"发送监控异常通知失败: {notify_err}")

                    await asyncio.sleep(10)  # 出错后等待更长时间

        except asyncio.CancelledError:
            logger.info(f"策略监控循环被取消: strategy_id={strategy_id}")
        except Exception as e:
            logger.error(f"策略监控循环异常退出: {e}")
        finally:
            current_task = asyncio.current_task()
            if self.strategy_tasks.get(strategy_id) is current_task:
                self.strategy_tasks.pop(strategy_id, None)
            if self.strategies.get(strategy_id) is strategy:
                self.strategies.pop(strategy_id, None)
            logger.info(f"策略监控循环结束: strategy_id={strategy_id}")

    async def start_strategy(
        self,
        strategy_id: int,
        strategy_type: StrategyType,
        symbol: str,
        parameters: dict,
        exchange: OKXExchange,
        user_id: int = 1
    ) -> bool:
        """启动策略"""
        try:
            # 检查策略是否已在运行
            if strategy_id in self.strategies:
                logger.warning(f"策略 {strategy_id} 已在运行中")
                return False

            # 创建策略实例
            strategy = self.create_strategy(
                strategy_id=strategy_id,
                strategy_type=strategy_type,
                symbol=symbol,
                parameters=parameters,
                exchange=exchange,
                user_id=user_id
            )

            # 启动策略
            await strategy.start()
            self.log_strategy_event(
                strategy_id=strategy_id,
                event_type="start",
                level="success",
                title="策略启动",
                message=f"{symbol} 策略已启动",
                data={
                    "symbol": symbol,
                    "strategy_type": strategy_type.value if hasattr(strategy_type, "value") else str(strategy_type),
                },
                parameter_snapshot=parameters,
                user_id=user_id,
            )

            # 保存策略实例
            self.strategies[strategy_id] = strategy

            # 启动监控循环
            task = asyncio.create_task(self._run_strategy_loop(strategy_id, strategy))
            self.strategy_tasks[strategy_id] = task

            logger.info(f"策略 {strategy_id} 启动成功")
            return True

        except NotImplementedError as e:
            logger.error(f"策略类型未实现: {e}")
            raise
        except Exception as e:
            logger.error(f"启动策略 {strategy_id} 失败: {e}")
            raise

    async def stop_strategy(self, strategy_id: int, cancel_orders: bool = True, close_position: bool = True) -> bool:
        """停止策略"""
        try:
            strategy = self.strategies.get(strategy_id)
            if not strategy:
                logger.warning(f"策略 {strategy_id} 未在运行")
                return False

            # 停止策略（兼容有无 cancel_orders/close_position 参数的实现）
            stop_sig = inspect.signature(strategy.stop)
            kwargs = {}
            if 'cancel_orders' in stop_sig.parameters:
                kwargs['cancel_orders'] = cancel_orders
            if 'close_position' in stop_sig.parameters:
                kwargs['close_position'] = close_position
            await strategy.stop(**kwargs)
            self.log_strategy_event(
                strategy_id=strategy_id,
                event_type="stop",
                level="info",
                title="策略停止",
                message=f"{strategy.symbol} 策略已停止",
                data={
                    "cancel_orders": cancel_orders,
                    "close_position": close_position,
                    "realized_pnl": getattr(strategy, "realized_pnl", 0),
                    "unrealized_pnl": getattr(strategy, "_unrealized_pnl", 0),
                    "total_trades": getattr(strategy, "total_trades", 0),
                },
                parameter_snapshot=strategy.parameters if isinstance(strategy.parameters, dict) else None,
                user_id=strategy.user_id,
            )

            # 取消监控任务
            task = self.strategy_tasks.get(strategy_id)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # 移除策略实例
            self.strategies.pop(strategy_id, None)
            self.strategy_tasks.pop(strategy_id, None)

            logger.info(f"策略 {strategy_id} 已停止")
            return True

        except Exception as e:
            logger.error(f"停止策略 {strategy_id} 失败: {e}")
            raise

    def get_strategy(self, strategy_id: int) -> Optional[StrategyBase]:
        """获取策略实例"""
        return self.strategies.get(strategy_id)

    def get_all_strategies(self) -> Dict[int, StrategyBase]:
        """获取所有运行中的策略"""
        return self.strategies.copy()

    def is_strategy_running(self, strategy_id: int) -> bool:
        """检查策略是否在运行"""
        return strategy_id in self.strategies

    def get_strategy_stats(self, strategy_id: int) -> Optional[dict]:
        """获取策略统计信息"""
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return None

        realized = strategy.realized_pnl if hasattr(strategy, 'realized_pnl') else 0
        unrealized = getattr(strategy, '_unrealized_pnl', 0)
        runtime_profit_factor = strategy.runtime_profit_factor()
        if runtime_profit_factor is not None and not math.isfinite(runtime_profit_factor):
            runtime_profit_factor = None
        signal_status = None
        if hasattr(strategy, "get_signal_status"):
            try:
                signal_status = strategy.get_signal_status()
            except Exception as exc:
                logger.debug(f"获取策略 {strategy_id} 信号状态失败: {exc}")

        current_price = None
        if isinstance(signal_status, dict):
            current_price = signal_status.get("current_price")

        position_side = getattr(strategy, "_position_side", "")
        entry_price = float(getattr(strategy, "_entry_price", 0) or 0)
        position_qty = float(getattr(strategy, "_position_qty", 0) or 0)
        stop_px = float(getattr(strategy, "_stop_px", 0) or 0)
        take_profit_px = float(getattr(strategy, "_take_profit_px", 0) or 0)
        position_status = {
            "in_position": bool(position_side),
            "side": position_side,
            "entry_price": entry_price,
            "qty": position_qty,
            "stop_px": stop_px,
            "take_profit_px": take_profit_px,
            "current_price": current_price,
        }
        if current_price and stop_px > 0 and take_profit_px > 0:
            current_price = float(current_price)
            if position_side == "long":
                position_status["distance_to_stop_pct"] = (current_price - stop_px) / current_price * 100
                position_status["distance_to_take_profit_pct"] = (take_profit_px - current_price) / current_price * 100
            elif position_side == "short":
                position_status["distance_to_stop_pct"] = (stop_px - current_price) / current_price * 100
                position_status["distance_to_take_profit_pct"] = (current_price - take_profit_px) / current_price * 100

        risk_fuse = strategy.parameters.get("risk_fuse", {}) if isinstance(strategy.parameters, dict) else {}
        if not isinstance(risk_fuse, dict):
            risk_fuse = {}
        max_position_usd = float(strategy.parameters.get("max_position_usd", 0) or 0) if isinstance(strategy.parameters, dict) else 0
        risk_base_usd = float(
            risk_fuse.get("risk_base_usd")
            or (strategy.parameters.get("risk_base_usd") if isinstance(strategy.parameters, dict) else 0)
            or (strategy.parameters.get("initial_capital") if isinstance(strategy.parameters, dict) else 0)
            or max(max_position_usd * 2, 1000)
        )
        daily_loss_limit_pct = risk_fuse.get("daily_loss_limit_pct", 0.02)
        max_drawdown_pct = risk_fuse.get("max_drawdown_pct", 0.05)
        max_consecutive_losses_limit = int(risk_fuse.get("max_consecutive_losses", 3))
        profit_factor_window = int(risk_fuse.get("profit_factor_window", 10))
        min_profit_factor = risk_fuse.get("min_profit_factor", 0.8)
        daily_loss_limit_usd = (
            float(risk_fuse.get("daily_loss_limit_usd"))
            if risk_fuse.get("daily_loss_limit_usd") is not None
            else risk_base_usd * float(daily_loss_limit_pct or 0)
        )
        max_drawdown_limit_usd = risk_base_usd * float(max_drawdown_pct or 0)
        risk_status = {
            "enabled": bool(risk_fuse.get("enabled", True)),
            "risk_base_usd": round(risk_base_usd, 4),
            "daily_realized_pnl": round(strategy.daily_realized_pnl, 4),
            "daily_loss_limit_usd": round(daily_loss_limit_usd, 4),
            "daily_loss_limit_pct": float(daily_loss_limit_pct or 0) * 100,
            "max_runtime_drawdown": round(strategy.max_runtime_drawdown, 4),
            "max_drawdown_limit_usd": round(max_drawdown_limit_usd, 4),
            "max_drawdown_pct": float(max_drawdown_pct or 0) * 100,
            "consecutive_losses": strategy.consecutive_losses,
            "max_consecutive_losses": max_consecutive_losses_limit,
            "runtime_profit_factor": runtime_profit_factor,
            "min_profit_factor": float(min_profit_factor) if min_profit_factor is not None else None,
            "profit_factor_window": profit_factor_window,
        }

        # 返回通用策略状态信息
        return {
            "strategy_id": strategy_id,
            "is_running": strategy.is_running,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": round(realized + unrealized, 4),
            "total_trades": strategy.total_trades if hasattr(strategy, 'total_trades') else 0,
            "buy_count": getattr(strategy, '_buy_count', 0),
            "sell_count": getattr(strategy, '_sell_count', 0),
            "win_rate": strategy.win_rate if hasattr(strategy, 'win_rate') else 0,
            "consecutive_losses": strategy.consecutive_losses,
            "max_consecutive_losses": strategy.max_consecutive_losses,
            "trade_pnl_history": strategy.trade_pnl_history,
            "runtime_realized_pnl": round(strategy.runtime_realized_pnl, 4),
            "daily_realized_pnl": round(strategy.daily_realized_pnl, 4),
            "max_runtime_drawdown": round(strategy.max_runtime_drawdown, 4),
            "runtime_profit_factor": runtime_profit_factor,
            "signal_status": signal_status,
            "position_status": position_status,
            "risk_status": risk_status,
        }

    async def stop_all_strategies(self):
        """停止所有策略"""
        strategy_ids = list(self.strategies.keys())

        for strategy_id in strategy_ids:
            try:
                await self.stop_strategy(strategy_id)
            except Exception as e:
                logger.error(f"停止策略 {strategy_id} 时出错: {e}")

        # 确保所有任务都被取消
        for task in list(self.strategy_tasks.values()):
            if not task.done():
                task.cancel()

        self.strategy_tasks.clear()

        logger.info("所有策略已停止")


# 全局单例实例
strategy_manager = StrategyManager()
