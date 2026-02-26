"""
策略管理器 - 管理所有运行中的策略实例
"""
from typing import Dict, Optional
from loguru import logger
from .base import StrategyBase
from .grid_strategy import GridStrategy
from .swing_long_strategy import SwingLongStrategy
from .swing_short_strategy import SwingShortStrategy
from .ai_swing_long_strategy import AISwingLongStrategy
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

        # 根据策略类型创建对应的策略实例
        if strategy_type_enum == StrategyType.GRID:
            strategy = GridStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id
            )
        elif strategy_type_enum == StrategyType.SWING_LONG:
            strategy = SwingLongStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id
            )
        elif strategy_type_enum == StrategyType.AI_SWING_LONG:
            strategy = AISwingLongStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id
            )
        elif strategy_type_enum == StrategyType.SWING_SHORT:
            strategy = SwingShortStrategy(
                strategy_id=strategy_id,
                exchange=exchange,
                symbol=symbol,
                parameters=parameters,
                user_id=user_id
            )
        elif strategy_type_enum == StrategyType.MARTIN:
            # TODO: 实现马丁格尔策略
            raise NotImplementedError("马丁格尔策略尚未实现")
        elif strategy_type_enum == StrategyType.TREND:
            # TODO: 实现趋势跟踪策略
            raise NotImplementedError("趋势跟踪策略尚未实现")
        elif strategy_type_enum == StrategyType.ARBITRAGE:
            # TODO: 实现套利策略
            raise NotImplementedError("套利策略尚未实现")
        elif strategy_type_enum == StrategyType.CUSTOM:
            # TODO: 实现自定义策略
            raise NotImplementedError("自定义策略尚未实现")
        else:
            raise ValueError(f"不支持的策略类型: {strategy_type_enum}")

        logger.info(f"创建策略实例: ID={strategy_id}, 类型={strategy_type_enum}, 交易对={symbol}")
        return strategy

    async def _persist_strategy_state(self, strategy_id: int, strategy: StrategyBase):
        """持久化策略状态到数据库"""
        db = SessionLocal()
        try:
            # 查询策略记录
            db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if not db_strategy:
                logger.warning(f"策略 {strategy_id} 不存在于数据库中")
                return

            # 从GridStrategy获取运行时数据
            if isinstance(strategy, GridStrategy):
                # 计算未实现盈亏
                unrealized_pnl = await strategy._calculate_unrealized_pnl()
                total_pnl = float(strategy.realized_pnl + unrealized_pnl)

                # 计算胜率（简化版：基于已实现盈亏是否为正）
                # TODO: 后续可以基于真实的交易记录计算更精确的胜率
                win_rate = 0.0
                if strategy.total_trades > 0:
                    # 这里简化处理，实际应该统计盈利交易次数
                    win_rate = max(0.0, min(100.0, 50.0 + (total_pnl / 100)))  # 临时公式

                # 更新数据库字段
                db_strategy.total_profit = total_pnl
                db_strategy.total_trades = strategy.total_trades
                db_strategy.win_rate = win_rate

                db.commit()

                logger.debug(
                    f"策略 {strategy_id} 状态已更新: "
                    f"盈亏={total_pnl:.2f}, 交易数={strategy.total_trades}, 胜率={win_rate:.1f}%"
                )

                # 通过WebSocket广播策略状态更新
                try:
                    await broadcast_strategy_update(strategy_id, {
                        "strategy_id": strategy_id,
                        "total_profit": total_pnl,
                        "total_trades": strategy.total_trades,
                        "win_rate": win_rate,
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

        # 订单状态缓存 {order_id: last_status}
        order_status_cache = {}

        # 持久化计数器（每10次循环更新一次数据库，约50秒）
        persist_counter = 0

        try:
            while strategy.is_running:
                try:
                    # 1. 获取最新ticker并调用 on_tick
                    ticker = await strategy.exchange.get_ticker(strategy.symbol)
                    await strategy.on_tick(ticker)

                    # 2. 检查所有挂单的状态
                    if isinstance(strategy, GridStrategy):
                        for grid_index, orders in list(strategy.grid_orders.items()):
                            for side in ["buy", "sell"]:
                                order_info = orders.get(side)
                                if not order_info:
                                    continue

                                order_id = order_info.get("order_id")
                                if not order_id:
                                    continue

                                try:
                                    # 查询订单最新状态
                                    order_detail = await strategy.exchange.get_order(
                                        symbol=strategy.symbol,
                                        order_id=order_id
                                    )

                                    current_status = order_detail.get("state")
                                    last_status = order_status_cache.get(order_id)

                                    # 如果状态发生变化，触发 on_order_update
                                    if current_status != last_status:
                                        logger.info(
                                            f"订单状态变化: {order_id} "
                                            f"{last_status} -> {current_status}"
                                        )

                                        # 更新订单信息中的状态
                                        order_info["status"] = current_status

                                        # 调用策略的订单更新处理
                                        await strategy.on_order_update({
                                            "order_id": order_id,
                                            "status": current_status,
                                            "side": side,
                                            "price": order_detail.get("px") or order_detail.get("avgPx"),
                                            "size": order_detail.get("sz"),
                                            "filled_size": order_detail.get("accFillSz"),
                                        })

                                        # 更新缓存
                                        order_status_cache[order_id] = current_status

                                except Exception as e:
                                    logger.error(f"查询订单 {order_id} 状态失败: {e}")

                    # 2.1 波段策略订单状态检查
                    elif isinstance(strategy, SwingLongStrategy):
                        from app.core.database import SessionLocal
                        from app.models.order import Order as OrderModel, OrderStatus

                        db = SessionLocal()
                        try:
                            # 查询该策略的所有未完成订单
                            pending_orders = db.query(OrderModel).filter(
                                OrderModel.strategy_id == strategy_id,
                                OrderModel.status.in_([OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED])
                            ).all()

                            for db_order in pending_orders:
                                order_id = db_order.order_id
                                if not order_id:
                                    continue

                                try:
                                    # 查询订单最新状态
                                    order_detail = await strategy.exchange.get_order(
                                        symbol=strategy.symbol,
                                        order_id=order_id
                                    )

                                    current_status = order_detail.get("state")

                                    # OKX状态映射
                                    status_map = {
                                        "live": OrderStatus.SUBMITTED,
                                        "partially_filled": OrderStatus.PARTIAL_FILLED,
                                        "filled": OrderStatus.FILLED,
                                        "canceled": OrderStatus.CANCELED,
                                    }

                                    new_db_status = status_map.get(current_status, OrderStatus.SUBMITTED)

                                    # 如果状态发生变化,更新数据库
                                    if new_db_status != db_order.status:
                                        logger.info(
                                            f"波段策略订单状态变化: {order_id} "
                                            f"{db_order.status} -> {new_db_status}"
                                        )

                                        db_order.status = new_db_status
                                        db_order.filled_amount = float(order_detail.get("accFillSz", 0))
                                        db_order.avg_price = float(order_detail.get("avgPx")) if order_detail.get("avgPx") else None

                                        if new_db_status == OrderStatus.FILLED:
                                            from datetime import datetime
                                            db_order.filled_at = datetime.now()
                                        elif new_db_status == OrderStatus.CANCELED:
                                            from datetime import datetime
                                            db_order.canceled_at = datetime.now()

                                        db.commit()

                                        # 调用策略的订单更新处理
                                        await strategy.on_order_update({
                                            "ordId": order_id,
                                            "state": current_status,
                                            "side": db_order.side.value,
                                            "avgPx": order_detail.get("avgPx"),
                                            "sz": order_detail.get("sz"),
                                            "accFillSz": order_detail.get("accFillSz"),
                                        })

                                except Exception as e:
                                    logger.error(f"查询波段策略订单 {order_id} 状态失败: {e}")

                        finally:
                            db.close()

                    # 3. 定期持久化策略状态到数据库
                    persist_counter += 1
                    if persist_counter >= 10:  # 每10次循环（约50秒）更新一次
                        persist_counter = 0
                        try:
                            await self._persist_strategy_state(strategy_id, strategy)
                        except Exception as e:
                            logger.error(f"持久化策略状态失败: {e}")

                    # 4. 每次循环都广播策略实时统计（用于Dashboard实时更新）
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

            # 检查策略是否成功启动（余额不足等原因可能导致启动失败）
            if not strategy.is_running:
                error_msg = "策略启动后立即停止（可能是余额不足或参数错误）"
                logger.error(error_msg)
                # 不发送通知，因为网格策略内部已经发送了
                raise ValueError(error_msg)

            # 添加到运行列表
            self.strategies[strategy_id] = strategy

            # 创建并启动监控任务
            task = asyncio.create_task(self._run_strategy_loop(strategy_id, strategy))
            self.strategy_tasks[strategy_id] = task

            logger.info(f"策略 {strategy_id} 启动成功，监控任务已创建")

            # 发送策略启动成功通知
            try:
                await broadcast_notification({
                    "type": "success",
                    "title": "策略启动成功",
                    "message": f"策略 {symbol} 已成功启动并开始运行",
                    "strategy_id": strategy_id,
                    "timestamp": time.time()
                })
            except Exception as e:
                logger.error(f"发送策略启动通知失败: {e}")

            return True

        except Exception as e:
            logger.error(f"启动策略 {strategy_id} 失败: {e}")

            # 只有在非余额不足异常时才发送通知（余额不足通知已在网格策略中发送）
            from app.services.strategy.base import InsufficientBalanceError
            if not isinstance(e.__cause__, InsufficientBalanceError):
                # 发送策略启动失败通知
                try:
                    await broadcast_notification({
                        "type": "error",
                        "title": "策略启动失败",
                        "message": f"策略 {symbol} 启动失败: {str(e)}",
                        "strategy_id": strategy_id,
                        "timestamp": time.time()
                    })
                except Exception as notify_err:
                    logger.error(f"发送策略启动失败通知失败: {notify_err}")

            # 清理已创建的资源
            if strategy_id in self.strategies:
                del self.strategies[strategy_id]
            if strategy_id in self.strategy_tasks:
                self.strategy_tasks[strategy_id].cancel()
                del self.strategy_tasks[strategy_id]
            raise

    async def stop_strategy(self, strategy_id: int, cancel_orders: bool = True) -> bool:
        """
        停止策略

        Args:
            strategy_id: 策略ID
            cancel_orders: 是否撤销所有未成交订单，默认True
        """
        try:
            # 检查策略是否在运行
            if strategy_id not in self.strategies:
                logger.warning(f"策略 {strategy_id} 未在运行")
                return False

            # 获取策略实例
            strategy = self.strategies[strategy_id]

            # 停止策略（传递 cancel_orders 参数）
            await strategy.stop(cancel_orders=cancel_orders)

            # 取消监控任务
            if strategy_id in self.strategy_tasks:
                task = self.strategy_tasks[strategy_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"策略 {strategy_id} 监控任务已取消")
                del self.strategy_tasks[strategy_id]

            # 从运行列表中移除
            del self.strategies[strategy_id]

            logger.info(f"策略 {strategy_id} 停止成功")

            # 发送策略停止通知
            try:
                await broadcast_notification({
                    "type": "info",
                    "title": "策略已停止",
                    "message": f"策略 {strategy.symbol} 已成功停止运行",
                    "strategy_id": strategy_id,
                    "timestamp": time.time()
                })
            except Exception as e:
                logger.error(f"发送策略停止通知失败: {e}")

            return True

        except Exception as e:
            logger.error(f"停止策略 {strategy_id} 失败: {e}")
            raise

    def get_strategy(self, strategy_id: int) -> Optional[StrategyBase]:
        """获取运行中的策略实例"""
        return self.strategies.get(strategy_id)

    def get_running_strategies(self) -> Dict[int, StrategyBase]:
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

        # 获取策略状态信息
        if isinstance(strategy, GridStrategy):
            # 构建网格订单详情列表
            grid_orders_detail = []
            for grid_index in range(strategy.grid_num):
                buy_price = float(strategy.grid_prices[grid_index])
                sell_price = float(strategy.grid_prices[grid_index + 1]) if grid_index < strategy.grid_num else None

                # 获取该网格的订单信息
                grid_order = strategy.grid_orders.get(grid_index, {})
                buy_order = grid_order.get("buy", {})
                sell_order = grid_order.get("sell", {})

                grid_orders_detail.append({
                    "grid_index": grid_index,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "buy_status": buy_order.get("status") if buy_order else None,
                    "buy_order_id": buy_order.get("order_id") if buy_order else None,
                    "buy_filled_amount": float(buy_order.get("filled_amount", 0)) if buy_order else 0,
                    "sell_status": sell_order.get("status") if sell_order else None,
                    "sell_order_id": sell_order.get("order_id") if sell_order else None,
                    "sell_filled_amount": float(sell_order.get("filled_amount", 0)) if sell_order else 0,
                })

            return {
                "strategy_id": strategy_id,
                "is_running": strategy.is_running,
                "position_size": float(strategy.position_size),
                "position_cost": float(strategy.position_cost),
                "realized_pnl": float(strategy.realized_pnl),
                "total_trades": strategy.total_trades,
                "total_buy_volume": float(strategy.total_buy_volume),
                "total_sell_volume": float(strategy.total_sell_volume),
                "grid_orders": len(strategy.grid_orders),
                "grid_orders_detail": grid_orders_detail,
            }

        # 处理波段做多策略 (包括AI增强版本)
        from .swing_long_strategy import SwingLongStrategy
        from .ai_swing_long_strategy import AISwingLongStrategy
        if isinstance(strategy, (SwingLongStrategy, AISwingLongStrategy)):
            position_info = strategy.position or {}
            stats = {
                "strategy_id": strategy_id,
                "is_running": strategy.is_running,
                "position_size": float(position_info.get("amount", 0)) if position_info else 0.0,
                "position_cost": float(position_info.get("entry_price", 0)) if position_info else 0.0,
                "realized_pnl": 0.0,  # 波段策略的已实现盈亏需要从订单计算
                "total_trades": 0,  # 从数据库统计
                "current_position": float(position_info.get("amount", 0)) if position_info else 0.0,
                "entry_price": float(position_info.get("entry_price", 0)) if position_info else 0.0,
                "highest_price": float(strategy.highest_price) if hasattr(strategy, 'highest_price') else 0.0,
                "waiting_reentry": strategy.waiting_reentry if hasattr(strategy, 'waiting_reentry') else False,
                "reentry_trigger_price": float(strategy.reentry_trigger_price) if hasattr(strategy, 'reentry_trigger_price') else 0.0,
            }

            # AI增强策略的额外信息
            if isinstance(strategy, AISwingLongStrategy):
                stats["ai_enabled"] = strategy.enable_ai
                stats["ai_last_analysis"] = strategy.last_ai_analysis_time.isoformat() if strategy.last_ai_analysis_time else None
                stats["ai_last_result"] = strategy.last_ai_result

            return stats

        return {
            "strategy_id": strategy_id,
            "is_running": strategy.is_running,
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


# 全局策略管理器实例
strategy_manager = StrategyManager()
