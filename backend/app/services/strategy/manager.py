"""
策略管理器 - 管理所有运行中的策略实例
"""
from typing import Dict, Optional
from loguru import logger
from .base import StrategyBase
from app.services.exchange.okx import OKXExchange
from app.models.strategy import StrategyType, Strategy
from app.core.database import SessionLocal
from app.websocket.manager import broadcast_strategy_stats, broadcast_strategy_update, broadcast_notification
import asyncio
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

        if strategy_type_enum == StrategyType.TREND:
            from app.services.strategy.trend_follow import TrendFollowStrategy
            return TrendFollowStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id,
            )
        elif strategy_type_enum == StrategyType.ORDER_BOOK_IMBALANCE:
            from app.services.strategy.order_book_imbalance import OrderBookImbalanceStrategy
            return OrderBookImbalanceStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id,
            )
        elif strategy_type_enum == StrategyType.GRID:
            from app.services.strategy.grid_strategy import GridStrategy
            return GridStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id,
            )
        elif strategy_type_enum == StrategyType.SWING_LONG:
            raise NotImplementedError("波段做多策略已移除")
        elif strategy_type_enum == StrategyType.AI_SWING_LONG:
            raise NotImplementedError("AI波段做多策略已移除")
        elif strategy_type_enum == StrategyType.SWING_SHORT:
            raise NotImplementedError("波段做空策略已移除")
        elif strategy_type_enum == StrategyType.DUAL_SIDE:
            from app.services.strategy.dual_side_strategy import DualSideStrategy
            return DualSideStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id,
            )
        elif strategy_type_enum == StrategyType.MARTIN:
            raise NotImplementedError("马丁格尔策略尚未实现")
        elif strategy_type_enum == StrategyType.ARBITRAGE:
            raise NotImplementedError("套利策略尚未实现")
        elif strategy_type_enum == StrategyType.CUSTOM:
            raise NotImplementedError("自定义策略尚未实现")
        else:
            raise ValueError(f"不支持的策略类型: {strategy_type_enum}")

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
            import inspect
            stop_sig = inspect.signature(strategy.stop)
            kwargs = {}
            if 'cancel_orders' in stop_sig.parameters:
                kwargs['cancel_orders'] = cancel_orders
            if 'close_position' in stop_sig.parameters:
                kwargs['close_position'] = close_position
            await strategy.stop(**kwargs)

            # 取消监控任务
            task = self.strategy_tasks.get(strategy_id)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # 移除策略实例
            del self.strategies[strategy_id]
            if strategy_id in self.strategy_tasks:
                del self.strategy_tasks[strategy_id]

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
