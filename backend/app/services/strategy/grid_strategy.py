"""
网格交易策略 - VERSION 2.0 WITH ORDER RECOVERY
"""
from typing import Dict, Optional
from decimal import Decimal
from .base import StrategyBase, InsufficientBalanceError
from loguru import logger
from app.websocket.manager import (
    broadcast_notification,
    broadcast_strategy_update,
    broadcast_strategy_stats,
    broadcast_position_update,
    broadcast_order_update
)
import time


def safe_decimal(value, default=0) -> Decimal:
    """
    安全地将值转换为Decimal类型

    Args:
        value: 要转换的值（可能是str、int、float、None或空字符串）
        default: 默认值

    Returns:
        Decimal: 转换后的Decimal值
    """
    if value is None or value == '' or value == "":
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(str(default))


class GridStrategy(StrategyBase):
    """
    网格交易策略

    参数说明：
    - grid_num: 网格数量
    - price_upper: 价格上限
    - price_lower: 价格下限
    - total_amount: 总投入金额（USDT）
    - min_order_size: 最小订单数量（BTC等）
    """

    def __init__(self, strategy_id: int, exchange, symbol: str, parameters: Dict, user_id: int = 1):
        super().__init__(strategy_id, exchange, symbol, parameters, user_id)

        # 网格参数
        self.grid_num = parameters.get("grid_num", 10)
        self.price_upper = Decimal(str(parameters.get("price_upper", 0)))
        self.price_lower = Decimal(str(parameters.get("price_lower", 0)))
        self.total_amount = Decimal(str(parameters.get("total_amount", 0)))
        # OKX BTC-USDT最小订单量为0.001 BTC
        self.min_order_size = Decimal(str(parameters.get("min_order_size", "0.001")))

        # 交易对精度信息（将在start时获取）
        self.lot_sz = None  # 下单数量精度
        self.min_sz = None  # 最小下单数量
        self.tick_sz = None  # 下单价格精度

        # 风险控制参数
        self.stop_loss = Decimal(str(parameters.get("stop_loss", "0")))  # 止损金额（USDT）
        self.stop_loss_pct = Decimal(str(parameters.get("stop_loss_pct", "0")))  # 止损百分比（如0.1表示10%）
        self.take_profit = Decimal(str(parameters.get("take_profit", "0")))  # 止盈金额（USDT）
        self.take_profit_pct = Decimal(str(parameters.get("take_profit_pct", "0")))  # 止盈百分比
        self.max_position = Decimal(str(parameters.get("max_position", "0")))  # 最大持仓数量

        # 计算每格价差
        if self.grid_num > 0:
            self.grid_step = (self.price_upper - self.price_lower) / self.grid_num
        else:
            self.grid_step = Decimal(0)

        # 计算每格投入金额（USDT）
        self.amount_per_grid = self.total_amount / self.grid_num if self.grid_num > 0 else Decimal(0)

        # 网格价格点位列表
        self.grid_prices = []
        self._calculate_grid_prices()

        # 网格订单记录 {grid_index: {"buy": order_info, "sell": order_info}}
        self.grid_orders = {}

        # 持仓和盈亏统计
        self.position_size = Decimal(0)  # 当前持仓数量
        self.position_cost = Decimal(0)  # 持仓成本（USDT）
        self.realized_pnl = Decimal(0)  # 已实现盈亏
        self.total_buy_volume = Decimal(0)  # 累计买入量
        self.total_sell_volume = Decimal(0)  # 累计卖出量
        self.total_trades = 0  # 总交易次数
        self.start_time = None  # 策略启动时间
        self.sync_task = None  # 订单状态同步任务

        logger.info(
            f"网格策略初始化：{symbol}, "
            f"网格数={self.grid_num}, "
            f"价格区间=[{self.price_lower}, {self.price_upper}], "
            f"每格价差={self.grid_step}, "
            f"每格金额={self.amount_per_grid} USDT"
        )

        if self.stop_loss > 0 or self.stop_loss_pct > 0:
            logger.info(f"止损设置: 金额={self.stop_loss} USDT, 百分比={self.stop_loss_pct * 100}%")
        if self.take_profit > 0 or self.take_profit_pct > 0:
            logger.info(f"止盈设置: 金额={self.take_profit} USDT, 百分比={self.take_profit_pct * 100}%")
        if self.max_position > 0:
            logger.info(f"最大持仓: {self.max_position}")

    def _calculate_grid_prices(self):
        """计算所有网格价格点位"""
        self.grid_prices = []
        for i in range(self.grid_num + 1):
            price = self.price_lower + i * self.grid_step
            # 调整价格精度
            price = self._round_price(price)
            self.grid_prices.append(price)
        logger.info(f"网格价格点位: {[float(p) for p in self.grid_prices]}")

    def _get_grid_index(self, price: Decimal) -> Optional[int]:
        """根据价格获取对应的网格索引"""
        if price < self.price_lower or price > self.price_upper:
            return None

        for i in range(len(self.grid_prices) - 1):
            if self.grid_prices[i] <= price < self.grid_prices[i + 1]:
                return i

        if price == self.price_upper:
            return self.grid_num - 1

        return None

    def _round_size(self, size: Decimal) -> Decimal:
        """根据lotSz调整数量精度,确保是lotSz的整数倍"""
        if not self.lot_sz:
            return size

        from decimal import ROUND_DOWN

        # 计算是lotSz的多少倍(向下取整)
        # 例如: size=1906.19536367, lotSz=0.01
        # multiplier = 1906.19536367 / 0.01 = 190619.536367
        # 向下取整 = 190619
        # result = 190619 * 0.01 = 1906.19
        multiplier = (size / self.lot_sz).quantize(Decimal("1"), rounding=ROUND_DOWN)
        result = multiplier * self.lot_sz

        return result

    def _round_price(self, price: Decimal) -> Decimal:
        """根据tickSz调整价格精度,确保是tickSz的整数倍"""
        if not self.tick_sz:
            return price

        from decimal import ROUND_HALF_UP

        # 计算是tickSz的多少倍(四舍五入)
        # 例如: price=0.00001071473684, tickSz=0.00000001
        # multiplier = 0.00001071473684 / 0.00000001 = 1071.473684
        # 四舍五入 = 1071
        # result = 1071 * 0.00000001 = 0.00001071
        multiplier = (price / self.tick_sz).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        result = multiplier * self.tick_sz

        return result

    async def _calculate_unrealized_pnl(self) -> Decimal:
        """计算未实现盈亏"""
        if self.position_size == 0:
            return Decimal(0)

        try:
            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = safe_decimal(ticker.get("last"), 0)

            # 未实现盈亏 = 持仓数量 * (当前价格 - 平均成本)
            avg_cost = self.position_cost / self.position_size if self.position_size > 0 else Decimal(0)
            unrealized_pnl = self.position_size * (current_price - avg_cost)

            return unrealized_pnl
        except Exception as e:
            logger.error(f"计算未实现盈亏失败: {e}")
            return Decimal(0)

    def _calculate_total_pnl(self, unrealized_pnl: Decimal) -> Decimal:
        """计算总盈亏"""
        return self.realized_pnl + unrealized_pnl

    async def _save_stats_to_db(self):
        """保存策略统计数据到数据库"""
        from app.core.database import SessionLocal
        from app.models.strategy import Strategy

        db = SessionLocal()
        try:
            strategy = db.query(Strategy).filter(Strategy.id == self.strategy_id).first()
            if strategy:
                # 使用修复后的 calculate_pnl() 方法获取正确的实时PNL数据
                pnl_data = await self.calculate_pnl(db)

                total_pnl = Decimal(str(pnl_data.get('total_pnl', 0)))
                realized_pnl = Decimal(str(pnl_data.get('realized_pnl', 0)))
                buy_count = pnl_data.get('buy_count', 0)
                sell_count = pnl_data.get('sell_count', 0)
                total_trades = buy_count + sell_count

                # 计算胜率：已配对交易的盈利比例
                win_rate = None
                if sell_count > 0:
                    # 如果有卖出交易，说明有完成的买卖对
                    # 已实现盈亏为正说明整体盈利，计算简化胜率
                    if realized_pnl > 0:
                        # 盈利的情况：胜率至少50%
                        win_rate = min(50 + float(realized_pnl / self.total_amount * 100), 100) if self.total_amount > 0 else 50
                    elif realized_pnl < 0:
                        # 亏损的情况：胜率低于50%
                        win_rate = max(50 + float(realized_pnl / self.total_amount * 100), 0) if self.total_amount > 0 else 50
                    else:
                        # 盈亏平衡：50%胜率
                        win_rate = 50.0

                # 更新数据库中的统计数据
                strategy.total_profit = float(total_pnl)
                strategy.total_trades = total_trades
                if win_rate is not None:
                    strategy.win_rate = win_rate

                db.commit()
                logger.info(f"已保存策略统计到数据库: 总盈亏={total_pnl}, 已实现={realized_pnl}, 总交易={total_trades}, 胜率={win_rate}")
            else:
                logger.warning(f"数据库中未找到策略 ID={self.strategy_id}")
        except Exception as e:
            logger.error(f"保存策略统计到数据库失败: {e}")
            db.rollback()
        finally:
            db.close()

    async def _check_risk_control(self):
        """检查风险控制条件"""
        if not self.is_running:
            return

        # 计算当前盈亏
        unrealized_pnl = await self._calculate_unrealized_pnl()
        total_pnl = self._calculate_total_pnl(unrealized_pnl)

        logger.debug(
            f"盈亏统计: 已实现={self.realized_pnl}, "
            f"未实现={unrealized_pnl}, 总计={total_pnl}"
        )

        # 检查止损
        if self.stop_loss > 0 and total_pnl <= -self.stop_loss:
            logger.warning(f"触发止损: 当前亏损 {total_pnl} USDT >= 止损线 {self.stop_loss} USDT")

            # 保存告警到数据库并发送通知
            try:
                from app.models.alert import Alert
                from app.core.database import SessionLocal
                import json

                alert_title = "策略止损"
                alert_message = f"策略 {self.symbol} 触发止损: 当前亏损 {float(total_pnl):.2f} USDT (止损线: {float(self.stop_loss):.2f} USDT)"

                # 保存到数据库
                db = SessionLocal()
                try:
                    alert = Alert(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        alert_type="stop_loss",
                        severity="error",
                        title=alert_title,
                        message=alert_message,
                        data=json.dumps({
                            "pnl": float(total_pnl),
                            "threshold": float(self.stop_loss),
                            "symbol": self.symbol
                        })
                    )
                    db.add(alert)
                    db.commit()
                    logger.info(f"止损告警已保存到数据库: ID={alert.id}")
                except Exception as db_error:
                    logger.error(f"保存止损告警到数据库失败: {db_error}")
                    db.rollback()
                finally:
                    db.close()

                # 发送WebSocket通知
                await broadcast_notification({
                    "type": "error",
                    "title": alert_title,
                    "message": alert_message,
                    "strategy_id": self.strategy_id,
                    "timestamp": time.time()
                })
            except Exception as e:
                logger.error(f"发送止损通知失败: {e}")

            await self.stop()
            return

        # 检查百分比止损
        if self.stop_loss_pct > 0:
            loss_pct = abs(total_pnl / self.total_amount) if self.total_amount > 0 else Decimal(0)
            if total_pnl < 0 and loss_pct >= self.stop_loss_pct:
                logger.warning(
                    f"触发止损: 当前亏损比例 {loss_pct * 100}% >= "
                    f"止损比例 {self.stop_loss_pct * 100}%"
                )

                # 保存告警到数据库并发送通知
                try:
                    from app.models.alert import Alert
                    from app.core.database import SessionLocal
                    import json

                    alert_title = "策略止损"
                    alert_message = f"策略 {self.symbol} 触发止损: 当前亏损比例 {float(loss_pct * 100):.2f}% (止损线: {float(self.stop_loss_pct * 100):.2f}%)"

                    # 保存到数据库
                    db = SessionLocal()
                    try:
                        alert = Alert(
                            user_id=self.user_id,
                            strategy_id=self.strategy_id,
                            alert_type="stop_loss",
                            severity="error",
                            title=alert_title,
                            message=alert_message,
                            data=json.dumps({
                                "pnl": float(total_pnl),
                                "loss_pct": float(loss_pct * 100),
                                "threshold_pct": float(self.stop_loss_pct * 100),
                                "symbol": self.symbol
                            })
                        )
                        db.add(alert)
                        db.commit()
                        logger.info(f"百分比止损告警已保存到数据库: ID={alert.id}")
                    except Exception as db_error:
                        logger.error(f"保存百分比止损告警到数据库失败: {db_error}")
                        db.rollback()
                    finally:
                        db.close()

                    # 发送WebSocket通知
                    await broadcast_notification({
                        "type": "error",
                        "title": alert_title,
                        "message": alert_message,
                        "strategy_id": self.strategy_id,
                        "timestamp": time.time()
                    })
                except Exception as e:
                    logger.error(f"发送止损通知失败: {e}")

                await self.stop()
                return

        # 检查止盈
        if self.take_profit > 0 and total_pnl >= self.take_profit:
            logger.info(f"触发止盈: 当前盈利 {total_pnl} USDT >= 止盈目标 {self.take_profit} USDT")

            # 保存告警到数据库并发送通知
            try:
                from app.models.alert import Alert
                from app.core.database import SessionLocal
                import json

                alert_title = "策略止盈"
                alert_message = f"策略 {self.symbol} 触发止盈: 当前盈利 {float(total_pnl):.2f} USDT (止盈目标: {float(self.take_profit):.2f} USDT)"

                # 保存到数据库
                db = SessionLocal()
                try:
                    alert = Alert(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        alert_type="take_profit",
                        severity="success",
                        title=alert_title,
                        message=alert_message,
                        data=json.dumps({
                            "pnl": float(total_pnl),
                            "threshold": float(self.take_profit),
                            "symbol": self.symbol
                        })
                    )
                    db.add(alert)
                    db.commit()
                    logger.info(f"止盈告警已保存到数据库: ID={alert.id}")
                except Exception as db_error:
                    logger.error(f"保存止盈告警到数据库失败: {db_error}")
                    db.rollback()
                finally:
                    db.close()

                # 发送WebSocket通知
                await broadcast_notification({
                    "type": "success",
                    "title": alert_title,
                    "message": alert_message,
                    "strategy_id": self.strategy_id,
                    "timestamp": time.time()
                })
            except Exception as e:
                logger.error(f"发送止盈通知失败: {e}")

            await self.stop()
            return

        # 检查百分比止盈
        if self.take_profit_pct > 0:
            profit_pct = total_pnl / self.total_amount if self.total_amount > 0 else Decimal(0)
            if total_pnl > 0 and profit_pct >= self.take_profit_pct:
                logger.info(
                    f"触发止盈: 当前盈利比例 {profit_pct * 100}% >= "
                    f"止盈比例 {self.take_profit_pct * 100}%"
                )

                # 保存告警到数据库并发送通知
                try:
                    from app.models.alert import Alert
                    from app.core.database import SessionLocal
                    import json

                    alert_title = "策略止盈"
                    alert_message = f"策略 {self.symbol} 触发止盈: 当前盈利比例 {float(profit_pct * 100):.2f}% (止盈目标: {float(self.take_profit_pct * 100):.2f}%)"

                    # 保存到数据库
                    db = SessionLocal()
                    try:
                        alert = Alert(
                            user_id=self.user_id,
                            strategy_id=self.strategy_id,
                            alert_type="take_profit",
                            severity="success",
                            title=alert_title,
                            message=alert_message,
                            data=json.dumps({
                                "pnl": float(total_pnl),
                                "profit_pct": float(profit_pct * 100),
                                "threshold_pct": float(self.take_profit_pct * 100),
                                "symbol": self.symbol
                            })
                        )
                        db.add(alert)
                        db.commit()
                        logger.info(f"百分比止盈告警已保存到数据库: ID={alert.id}")
                    except Exception as db_error:
                        logger.error(f"保存百分比止盈告警到数据库失败: {db_error}")
                        db.rollback()
                    finally:
                        db.close()

                    # 发送WebSocket通知
                    await broadcast_notification({
                        "type": "success",
                        "title": alert_title,
                        "message": alert_message,
                        "strategy_id": self.strategy_id,
                        "timestamp": time.time()
                    })
                except Exception as e:
                    logger.error(f"发送止盈通知失败: {e}")

                await self.stop()
                return

    def _check_position_limit(self, additional_size: Decimal) -> bool:
        """检查持仓限制"""
        if self.max_position <= 0:
            return True

        new_position = self.position_size + additional_size
        if abs(new_position) > self.max_position:
            logger.warning(
                f"超过最大持仓限制: 当前={self.position_size}, "
                f"新增={additional_size}, 限制={self.max_position}"
            )
            return False

        return True

    async def _place_buy_order(self, grid_index: int) -> Optional[Dict]:
        """在指定网格挂买单"""
        try:
            price = self.grid_prices[grid_index]
            # 计算买入数量：每格金额 / 价格
            size = self.amount_per_grid / price

            # 根据lotSz调整数量精度
            size = self._round_size(size)

            if size < self.min_order_size:
                logger.warning(f"订单数量 {size} 小于最小数量 {self.min_order_size}，跳过")
                return None

            # 检查持仓限制
            if not self._check_position_limit(size):
                logger.warning(f"买单被拒绝：超过持仓限制")
                return None

            logger.info(f"在网格 {grid_index} 挂买单: 价格={price}, 数量={size} (已调整精度)")

            # 使用带重试的下单方法
            order = await self.place_order_with_retry(
                side="buy",
                amount=size,
                price=price,
                order_type="limit",
                max_retries=3,
                retry_delay=2.0
            )

            if order:
                if not self.grid_orders.get(grid_index):
                    self.grid_orders[grid_index] = {}
                self.grid_orders[grid_index]["buy"] = order
                logger.info(f"网格 {grid_index} 买单挂单成功: 订单ID={order.get('order_id')}")
            else:
                logger.error(f"网格 {grid_index} 买单挂单失败（重试后仍失败）")

            return order
        except InsufficientBalanceError:
            # 余额不足异常需要重新抛出，以便上层处理
            raise
        except Exception as e:
            logger.error(f"挂买单异常: {e}")
            return None

    async def _place_sell_order(self, grid_index: int) -> Optional[Dict]:
        """在指定网格挂卖单"""
        try:
            price = self.grid_prices[grid_index + 1]  # 卖单在上一格
            size = self.amount_per_grid / price

            # 根据lotSz调整数量精度
            size = self._round_size(size)

            if size < self.min_order_size:
                logger.warning(f"订单数量 {size} 小于最小数量 {self.min_order_size}，跳过")
                return None

            logger.info(f"在网格 {grid_index} 挂卖单: 价格={price}, 数量={size} (已调整精度)")

            # 使用带重试的下单方法
            order = await self.place_order_with_retry(
                side="sell",
                amount=size,
                price=price,
                order_type="limit",
                max_retries=3,
                retry_delay=2.0
            )

            if order:
                if not self.grid_orders.get(grid_index):
                    self.grid_orders[grid_index] = {}
                self.grid_orders[grid_index]["sell"] = order
                logger.info(f"网格 {grid_index} 卖单挂单成功: 订单ID={order.get('order_id')}")
            else:
                logger.error(f"网格 {grid_index} 卖单挂单失败（重试后仍失败）")

            return order
        except InsufficientBalanceError:
            # 余额不足异常需要重新抛出，以便上层处理
            raise
        except Exception as e:
            logger.error(f"挂卖单异常: {e}")
            return None

    async def on_tick(self, ticker: Dict):
        """处理实时行情"""
        if not self.is_running:
            return

        current_price = Decimal(str(ticker.get("last", 0)))
        logger.debug(f"当前价格: {current_price}")

        # 【核心修复】检查并补充网格订单
        await self._check_grid_orders(current_price)

        # 【新增】健康检查日志 - 每60秒打印一次
        if not hasattr(self, '_health_check_count'):
            self._health_check_count = 0

        self._health_check_count += 1
        if self._health_check_count >= 12:  # 60秒 (12 * 5秒)
            self._health_check_count = 0
            active_buy_orders = sum(1 for orders in self.grid_orders.values()
                                   if "buy" in orders and orders["buy"])
            active_sell_orders = sum(1 for orders in self.grid_orders.values()
                                    if "sell" in orders and orders["sell"])
            total_active = active_buy_orders + active_sell_orders

            logger.info(
                f"💊 网格健康检查 [{self.symbol}] "
                f"价格={current_price:.6f} | "
                f"买单={active_buy_orders} | "
                f"卖单={active_sell_orders} | "
                f"总订单={total_active} | "
                f"持仓={self.position_size:.6f} | "
                f"已实现盈亏={self.realized_pnl:.2f} USDT | "
                f"总交易={self.total_trades}笔"
            )

        # 【优化】降低风险检查频率 - 每30秒检查一次
        if not hasattr(self, '_risk_check_count'):
            self._risk_check_count = 0

        self._risk_check_count += 1
        if self._risk_check_count >= 6:  # 30秒 (6 * 5秒)
            self._risk_check_count = 0
            await self._check_risk_control()

    async def _check_grid_orders(self, current_price: Decimal):
        """【核心修复】检查并补充网格订单

        逻辑:
        1. 遍历所有网格价格
        2. 当前价格 > 网格价格 → 应该有卖单
        3. 当前价格 < 网格价格 → 应该有买单
        4. 如果缺少订单,自动补充
        """
        for i in range(len(self.grid_prices)):
            grid_price = self.grid_prices[i]

            # 价格在网格上方,应该有卖单
            if current_price > grid_price:
                has_sell = (
                    i in self.grid_orders and
                    "sell" in self.grid_orders[i] and
                    self.grid_orders[i]["sell"] is not None
                )

                if not has_sell:
                    logger.info(f"🔧 网格{i}价格{grid_price:.6f}缺少卖单,补充中...")
                    try:
                        await self._place_sell_order(i)
                    except Exception as e:
                        logger.error(f"补充网格{i}卖单失败: {e}")

            # 价格在网格下方,应该有买单
            elif current_price < grid_price:
                has_buy = (
                    i in self.grid_orders and
                    "buy" in self.grid_orders[i] and
                    self.grid_orders[i]["buy"] is not None
                )

                if not has_buy:
                    logger.info(f"🔧 网格{i}价格{grid_price:.6f}缺少买单,补充中...")
                    try:
                        await self._place_buy_order(i)
                    except Exception as e:
                        logger.error(f"补充网格{i}买单失败: {e}")

    async def on_kline(self, kline: Dict):
        """处理K线数据"""
        # 网格策略主要基于实时价格，K线数据可选用
        pass

    async def on_order_update(self, order: Dict):
        """处理订单更新"""
        logger.info(f"订单更新: {order}")

        if not self.is_running:
            return

        order_id = order.get("order_id")
        status = order.get("status")
        side = order.get("side")
        price = Decimal(str(order.get("price", 0)))
        size = Decimal(str(order.get("size", 0)))
        filled_size = Decimal(str(order.get("filled_size", size)))

        # 更新数据库中的订单状态
        from app.core.database import SessionLocal
        from app.models.order import Order as OrderModel, OrderStatus
        from datetime import datetime, timezone

        db = SessionLocal()
        try:
            # 查找数据库中的订单记录
            db_order = db.query(OrderModel).filter(
                OrderModel.order_id == order_id,
                OrderModel.strategy_id == self.strategy_id
            ).first()

            if db_order:
                # 映射OKX订单状态到数据库状态
                status_mapping = {
                    "live": OrderStatus.PENDING,
                    "partially_filled": OrderStatus.PARTIAL_FILLED,
                    "filled": OrderStatus.FILLED,
                    "canceled": OrderStatus.CANCELED,
                }

                db_order.status = status_mapping.get(status, OrderStatus.PENDING)
                db_order.filled_amount = float(filled_size)

                if status == "filled":
                    db_order.filled_at = datetime.now(timezone.utc)
                    db_order.avg_price = float(price)

                db.commit()
                logger.info(f"已更新数据库中的订单 {order_id}: 状态={status}, 成交量={filled_size}")
            else:
                logger.warning(f"数据库中未找到订单 {order_id}")

        except Exception as e:
            logger.error(f"更新数据库订单状态失败: {e}")
            db.rollback()
        finally:
            db.close()

        # 【新增】处理订单撤销
        if status == "canceled":
            logger.warning(f"⚠️  订单已撤销: {order_id} - {side} @ {price}")

            # 找到被撤销订单对应的网格,清除记录
            for idx, grid_info in self.grid_orders.items():
                if side == "buy" and grid_info.get("buy", {}).get("order_id") == order_id:
                    logger.info(f"清除网格{idx}的买单记录,下次tick时会自动补充")
                    self.grid_orders[idx]["buy"] = None
                    break
                elif side == "sell" and grid_info.get("sell", {}).get("order_id") == order_id:
                    logger.info(f"清除网格{idx}的卖单记录,下次tick时会自动补充")
                    self.grid_orders[idx]["sell"] = None
                    break

            return

        # 【新增】处理部分成交
        if status == "partially_filled":
            logger.info(f"📊 订单部分成交: {order_id} - 已成交 {filled_size}/{size}")
            return

        # 只处理完全成交的订单
        if status != "filled":
            return

        logger.info(f"订单 {order_id} 成交: {side} @ {price}")

        # 推送订单成交事件
        try:
            side_cn = "买" if side == "buy" else "卖"
            await broadcast_order_update(self.strategy_id, {
                "strategy_id": self.strategy_id,
                "order_id": order_id,
                "symbol": self.symbol,
                "side": side,
                "type": "limit",
                "price": float(price),
                "amount": float(size),
                "filled": float(size),
                "status": "filled",
                "event": "filled",
                "message": f"网格{side_cn}单已完全成交",
                "timestamp": int(time.time() * 1000)
            })
        except Exception as e:
            logger.error(f"推送订单成交事件失败: {e}")

        # 更新统计信息（无论是否找到网格索引都要更新）
        self.total_trades += 1
        trade_amount = price * size

        # 根据成交方向更新持仓和成本
        if side == "buy":
            self.position_size += size
            self.position_cost += trade_amount
            self.total_buy_volume += size
        elif side == "sell":
            # 计算已实现盈亏
            if self.position_size > 0:
                avg_cost = self.position_cost / self.position_size
                realized = size * (price - avg_cost)
                self.realized_pnl += realized
                logger.info(f"卖单成交，实现盈亏: {realized} USDT")

            # 更新持仓和成本
            self.position_size -= size
            if self.position_size > 0:
                self.position_cost -= trade_amount
            else:
                self.position_cost = Decimal(0)

            self.total_sell_volume += size

        logger.info(
            f"当前状态: 持仓={self.position_size}, "
            f"成本={self.position_cost}, 已实现盈亏={self.realized_pnl}"
        )

        # 保存策略统计数据到数据库（关键：无论是否找到网格都要保存）
        await self._save_stats_to_db()

        # 推送持仓更新事件
        try:
            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = safe_decimal(ticker.get("last"), 0)
            avg_cost = self.position_cost / self.position_size if self.position_size > 0 else Decimal(0)
            floating_profit = self.position_size * (current_price - avg_cost) if self.position_size > 0 else Decimal(0)
            floating_profit_rate = (floating_profit / self.position_cost * 100) if self.position_cost > 0 else Decimal(0)

            await broadcast_position_update(self.strategy_id, {
                "strategy_id": self.strategy_id,
                "symbol": self.symbol,
                "position": float(self.position_size),
                "avg_cost": float(avg_cost),
                "current_price": float(current_price),
                "floating_profit": float(floating_profit),
                "floating_profit_rate": float(floating_profit_rate),
                "timestamp": int(time.time() * 1000)
            })
        except Exception as e:
            logger.error(f"推送持仓更新事件失败: {e}")

        # 找到对应的网格索引并挂反向订单
        grid_index = None
        for idx, grid_info in self.grid_orders.items():
            if side == "buy" and grid_info.get("buy", {}).get("order_id") == order_id:
                grid_index = idx
                break
            elif side == "sell" and grid_info.get("sell", {}).get("order_id") == order_id:
                grid_index = idx
                break

        if grid_index is None:
            logger.warning(f"未找到订单 {order_id} 对应的网格，跳过挂单操作（统计数据已更新）")
            return

        # 在相应位置挂反向订单
        if side == "buy":
            logger.info(f"买单成交，在网格 {grid_index} 挂卖单")
            await self._place_sell_order(grid_index)
        elif side == "sell" and grid_index > 0:
            logger.info(f"卖单成交，在网格 {grid_index - 1} 挂买单")
            await self._place_buy_order(grid_index - 1)

        # 检查风险控制
        await self._check_risk_control()

    async def _load_existing_orders(self):
        """从OKX加载该策略的未成交订单"""
        try:
            logger.info(f"检查策略 {self.strategy_id} 的现有未成交订单...")

            # 根据交易对名称判断类型
            if self.symbol.endswith("-SWAP"):
                inst_type = "SWAP"
            elif self.symbol.endswith("-FUTURES"):
                inst_type = "FUTURES"
            else:
                inst_type = "SPOT"

            # 查询该交易对的所有未成交订单
            pending_orders = await self.exchange.get_orders_pending(
                inst_type=inst_type,
                inst_id=self.symbol
            )

            if not pending_orders:
                logger.info("没有发现未成交订单")
                return

            logger.info(f"发现 {len(pending_orders)} 个未成交订单，开始恢复...")

            # 遍历所有未成交订单，恢复到grid_orders中
            for order in pending_orders:
                order_id = order.get("ordId")
                side = order.get("side")
                price = safe_decimal(order.get("px"), 0)
                size = safe_decimal(order.get("sz"), 0)
                state = order.get("state")

                # 找到订单对应的网格索引 - 使用最接近的网格点
                grid_index = None
                min_diff = None

                if side == "buy":
                    # 买单：找到价格最接近的网格点
                    for i, grid_price in enumerate(self.grid_prices[:-1]):
                        diff = abs(grid_price - price)
                        # 使用相对误差：允许5%的偏差
                        if diff / grid_price < Decimal("0.05"):
                            if min_diff is None or diff < min_diff:
                                min_diff = diff
                                grid_index = i
                elif side == "sell":
                    # 卖单：找到价格最接近的网格点（卖单在上一格）
                    for i, grid_price in enumerate(self.grid_prices[1:]):
                        diff = abs(grid_price - price)
                        # 使用相对误差：允许5%的偏差
                        if diff / grid_price < Decimal("0.05"):
                            if min_diff is None or diff < min_diff:
                                min_diff = diff
                                grid_index = i

                if grid_index is not None:
                    if not self.grid_orders.get(grid_index):
                        self.grid_orders[grid_index] = {}

                    self.grid_orders[grid_index][side] = {
                        "order_id": order_id,
                        "price": float(price),
                        "size": float(size),
                        "status": state,
                        "side": side
                    }
                    logger.info(f"恢复订单: 网格{grid_index} {side}单 ID={order_id} 价格={price}")
                else:
                    logger.warning(f"订单 {order_id} (价格={price}) 不在当前网格范围内，将被忽略")

            logger.info(f"订单恢复完成，已恢复 {sum(len(orders) for orders in self.grid_orders.values())} 个订单到 {len(self.grid_orders)} 个网格")

        except Exception as e:
            logger.error(f"加载现有订单失败: {e}")

    async def start(self):
        """启动策略"""
        await super().start()
        logger.info(f"启动网格策略 {self.strategy_id}")

        # 记录启动时间
        import time
        self.start_time = time.time()

        # 启动订单状态同步任务 (先启动,确保在策略运行期间始终同步)
        import asyncio
        self.sync_task = asyncio.create_task(self._sync_orders_status_loop())
        logger.info(f"已启动订单状态同步任务")

        try:
            # 根据交易对名称判断类型
            # BTC-USDT-SWAP -> SWAP, BTC-USDT -> SPOT
            if self.symbol.endswith("-SWAP"):
                inst_type = "SWAP"
            elif self.symbol.endswith("-FUTURES"):
                inst_type = "FUTURES"
            else:
                inst_type = "SPOT"

            # 获取交易对精度信息
            logger.info(f"查询交易对 {self.symbol} 的精度信息 (类型: {inst_type})...")
            instruments = await self.exchange.get_instruments(inst_type=inst_type)
            inst_info = next((inst for inst in instruments if inst.get("instId") == self.symbol), None)
            if inst_info:
                self.lot_sz = safe_decimal(inst_info.get("lotSz"), "0.00000001")
                self.min_sz = safe_decimal(inst_info.get("minSz"), "0.001")
                self.tick_sz = safe_decimal(inst_info.get("tickSz"), "0.00000001")
                logger.info(f"交易对精度信息: lotSz={self.lot_sz}, minSz={self.min_sz}, tickSz={self.tick_sz}")
            else:
                # 使用默认值
                self.lot_sz = Decimal("0.00000001")
                self.min_sz = Decimal("0.001")
                self.tick_sz = Decimal("0.00000001")
                logger.warning(f"未找到交易对 {self.symbol} 的精度信息，使用默认值")

            # 重新计算网格价格，应用正确的价格精度
            logger.info("根据tickSz重新计算网格价格...")
            self._calculate_grid_prices()

            # 对于永续合约/交割合约，设置杠杆倍数
            if inst_type in ["SWAP", "FUTURES"]:
                try:
                    # 获取保证金模式和杠杆倍数
                    margin_mode = self.parameters.get("margin_mode", "isolated")  # 默认逐仓
                    leverage = self.parameters.get("leverage", "10")
                    margin_mode_cn = "逐仓" if margin_mode == "isolated" else "全仓"
                    logger.info(f"为 {self.symbol} 设置杠杆倍数: {leverage}x ({margin_mode_cn}模式)")

                    leverage_result = await self.exchange.set_leverage(
                        lever=str(leverage),
                        mgn_mode=margin_mode,
                        inst_id=self.symbol,
                        pos_side="net"  # 买卖模式
                    )
                    logger.info(f"杠杆倍数设置成功: {leverage_result}")
                except Exception as e:
                    # 杠杆设置失败不影响策略启动（可能已经设置过了）
                    logger.warning(f"设置杠杆倍数失败（可能已设置）: {e}")

            # 先恢复已存在的未成交订单
            await self._load_existing_orders()

            # 获取当前价格
            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = safe_decimal(ticker.get("last"), 0)
            logger.info(f"当前市场价格: {current_price}")

            # 验证参数：检查每格订单量是否满足最小要求
            min_order_value = self.min_order_size * current_price
            if self.amount_per_grid < min_order_value:
                error_msg = (
                    f"参数错误：每格金额 {self.amount_per_grid} USDT 不足以支持最小订单量 "
                    f"{self.min_order_size} BTC (约需 {min_order_value} USDT)。"
                    f"建议增加总投入金额至 {min_order_value * self.grid_num} USDT 以上。"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 检查价格是否在网格范围内
            if current_price < self.price_lower or current_price > self.price_upper:
                logger.warning(f"当前价格 {current_price} 不在网格范围 [{self.price_lower}, {self.price_upper}] 内")
                return

            # 找到当前价格所在的网格区间
            current_grid_index = self._get_grid_index(current_price)
            if current_grid_index is None:
                logger.error(f"无法确定当前价格 {current_price} 的网格位置")
                return

            logger.info(f"当前价格位于网格 {current_grid_index}")

            # 在当前价格下方的所有网格挂买单（跳过已有订单的网格）
            try:
                new_orders_count = 0
                for i in range(current_grid_index + 1):
                    # 检查该网格是否已有买单
                    if self.grid_orders.get(i) and self.grid_orders[i].get("buy"):
                        logger.info(f"网格 {i} 已有买单，跳过")
                        continue

                    await self._place_buy_order(i)
                    new_orders_count += 1
                logger.info(f"本次新建 {new_orders_count} 个买单")
            except InsufficientBalanceError as balance_err:
                # 捕获余额不足异常
                logger.error(f"余额不足，停止初始化网格订单: {balance_err}")
                self.is_running = False

                # 发送通知给前端
                try:
                    await broadcast_notification({
                        "type": "error",
                        "title": "策略启动失败",
                        "message": f"账户USDT余额不足，无法完成网格订单初始化。请充值账户或减小策略参数（减少网格数量或总投入金额）。",
                        "strategy_id": self.strategy_id,
                        "timestamp": time.time()
                    })
                except Exception as notify_err:
                    logger.error(f"发送余额不足通知失败: {notify_err}")

                # 重新抛出异常，让外层处理
                raise

            # 在当前价格上方的所有网格挂卖单（需要有币才能卖）
            # 初始状态暂不挂卖单，等买单成交后再挂

            total_buy_orders = sum(1 for grid in self.grid_orders.values() if grid.get("buy"))
            logger.info(f"网格策略启动完成，当前共有 {total_buy_orders} 个买单（其中 {new_orders_count} 个为本次新建）")

            # 推送策略启动事件
            try:
                await broadcast_strategy_update(self.strategy_id, {
                    "strategy_id": self.strategy_id,
                    "status": "running",
                    "event": "started",
                    "message": f"网格策略已启动 ({total_buy_orders} 个买单)",
                    "timestamp": int(time.time() * 1000)
                })
            except Exception as e:
                logger.error(f"推送策略启动事件失败: {e}")

        except InsufficientBalanceError:
            # 余额不足异常已经处理过了，直接返回
            logger.error("策略因余额不足而停止")
            self.is_running = False
        except Exception as e:
            logger.error(f"启动网格策略失败: {e}")
            self.is_running = False

    async def _sync_orders_status_loop(self):
        """
        定时同步订单状态
        每5秒查询一次未完成订单的最新状态
        """
        from app.core.database import SessionLocal
        from app.models.order import Order as OrderModel, OrderStatus as OS
        from datetime import datetime, timezone
        import asyncio

        logger.info(f"启动订单状态同步任务（策略{self.strategy_id}）")

        while self.is_running:
            try:
                await asyncio.sleep(5)  # 每5秒同步一次

                db = SessionLocal()
                try:
                    # 查询所有未完成的订单
                    pending_orders = db.query(OrderModel).filter(
                        OrderModel.strategy_id == self.strategy_id,
                        OrderModel.status.in_([OS.PENDING, OS.SUBMITTED, OS.PARTIAL_FILLED])
                    ).all()

                    if not pending_orders:
                        continue

                    logger.debug(f"检查 {len(pending_orders)} 个未完成订单的状态")

                    # 批量查询订单状态
                    for order in pending_orders:
                        try:
                            # 从OKX API查询订单状态
                            okx_order = await self.exchange.get_order(
                                symbol=order.symbol,
                                order_id=order.order_id
                            )

                            if not okx_order:
                                continue

                            # 解析OKX订单状态
                            okx_state = okx_order.get('state', '')
                            okx_filled_sz = safe_decimal(okx_order.get('accFillSz'), 0)
                            okx_avg_px = safe_decimal(okx_order.get('avgPx'), 0)
                            okx_fee = safe_decimal(okx_order.get('fee'), 0)

                            # 检查状态是否变化
                            old_status = order.status
                            old_filled = order.filled_amount
                            status_changed = False

                            # 更新订单状态
                            if okx_state == 'filled':
                                order.status = OS.FILLED
                                order.filled_amount = okx_filled_sz
                                order.avg_price = okx_avg_px
                                order.fee = abs(okx_fee)  # 手续费取绝对值
                                order.filled_at = datetime.now(timezone.utc)
                                status_changed = True
                            elif okx_state == 'partially_filled':
                                order.status = OS.PARTIAL_FILLED
                                order.filled_amount = okx_filled_sz
                                order.avg_price = okx_avg_px
                                order.fee = abs(okx_fee)
                                status_changed = (old_filled != okx_filled_sz)
                            elif okx_state in ['canceled', 'mmp_canceled']:
                                order.status = OS.CANCELED
                                order.canceled_at = datetime.now(timezone.utc)
                                status_changed = True

                            # 如果状态有变化，提交并触发回调
                            if status_changed:
                                db.commit()
                                logger.info(
                                    f"订单状态同步: {order.order_id} "
                                    f"{old_status.value} -> {order.status.value}, "
                                    f"成交量: {old_filled} -> {order.filled_amount}"
                                )

                                # 触发订单更新回调
                                await self.on_order_update({
                                    "ordId": order.order_id,
                                    "instId": order.symbol,
                                    "side": order.side.value,
                                    "px": str(order.price),
                                    "sz": str(order.amount),
                                    "accFillSz": str(order.filled_amount),
                                    "avgPx": str(order.avg_price),
                                    "state": okx_state,
                                    "fee": str(order.fee)
                                })

                        except Exception as e:
                            logger.error(f"同步订单 {order.order_id} 状态失败: {e}")
                            continue

                finally:
                    db.close()

            except asyncio.CancelledError:
                logger.info(f"订单状态同步任务被取消（策略{self.strategy_id}）")
                break
            except Exception as e:
                logger.error(f"订单状态同步任务出错: {e}")
                await asyncio.sleep(5)

        logger.info(f"订单状态同步任务已停止（策略{self.strategy_id}）")

    async def cancel_all_orders(self) -> Dict:
        """
        撤销策略的所有未成交订单

        Returns:
            Dict: {
                "total": 总订单数,
                "canceled": 成功撤销数,
                "failed": 失败数,
                "errors": 错误列表
            }
        """
        from app.core.database import SessionLocal
        from app.models.order import Order as OrderModel, OrderStatus

        logger.info(f"开始撤销策略 {self.strategy_id} 的所有未成交订单")

        result = {
            "total": 0,
            "canceled": 0,
            "failed": 0,
            "errors": []
        }

        db = SessionLocal()
        try:
            # 从数据库查询所有未成交订单
            pending_orders = db.query(OrderModel).filter(
                OrderModel.strategy_id == self.strategy_id,
                OrderModel.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED])
            ).all()

            result["total"] = len(pending_orders)
            logger.info(f"找到 {result['total']} 个未成交订单")

            # 逐个撤销订单
            for order in pending_orders:
                try:
                    # 调用交易所API撤销订单
                    cancel_result = await self.exchange.cancel_order(
                        symbol=order.symbol,
                        order_id=order.order_id
                    )

                    # 更新数据库订单状态
                    order.status = OrderStatus.CANCELED
                    order.canceled_at = datetime.now(timezone.utc)

                    # 同步更新内存中的订单状态
                    side = order.side.value if hasattr(order.side, 'value') else str(order.side)
                    price = float(order.price)
                    if side in self.grid_orders and price in self.grid_orders[side]:
                        self.grid_orders[side][price]["status"] = "canceled"

                    result["canceled"] += 1
                    logger.info(f"✓ 撤销订单成功: {order.order_id} ({order.symbol} {side} @ {price})")

                except Exception as e:
                    result["failed"] += 1
                    error_msg = f"撤销订单 {order.order_id} 失败: {str(e)}"
                    result["errors"].append(error_msg)
                    logger.error(f"✗ {error_msg}")

            db.commit()

            logger.info(
                f"撤单完成: 总计 {result['total']} 个，"
                f"成功 {result['canceled']} 个，失败 {result['failed']} 个"
            )

        except Exception as e:
            db.rollback()
            logger.error(f"撤销订单过程中出错: {e}")
            result["errors"].append(f"撤单过程出错: {str(e)}")
        finally:
            db.close()

        return result

    async def stop(self, cancel_orders: bool = False):
        """
        停止策略

        Args:
            cancel_orders: 是否撤销所有未成交订单，默认False保持订单以便重启恢复
        """
        await super().stop()
        logger.info(f"停止网格策略 {self.strategy_id} (cancel_orders={cancel_orders})")

        # 取消订单状态同步任务
        if self.sync_task and not self.sync_task.done():
            self.sync_task.cancel()
            try:
                await self.sync_task
            except Exception:
                pass
            logger.info(f"已取消订单状态同步任务")

        try:
            pending_count = sum(
                1 for orders in self.grid_orders.values()
                for order in orders.values()
                if order and order.get("status") not in ["filled", "canceled"]
            )

            # 如果需要撤销订单
            cancel_result = None
            if cancel_orders and pending_count > 0:
                logger.info(f"正在撤销 {pending_count} 个未成交订单...")
                cancel_result = await self.cancel_all_orders()

                message = (
                    f"网格策略已停止并撤销订单: "
                    f"成功 {cancel_result['canceled']} 个，失败 {cancel_result['failed']} 个"
                )
            else:
                message = f"网格策略已停止 (保留 {pending_count} 个未成交订单以便重启恢复)"

            logger.info(f"{message}，最终持仓: {self.position_size}")

            # 推送策略停止事件
            try:
                event_data = {
                    "strategy_id": self.strategy_id,
                    "status": "stopped",
                    "event": "stopped",
                    "message": message,
                    "timestamp": int(time.time() * 1000)
                }

                if cancel_result:
                    event_data["cancel_result"] = cancel_result

                await broadcast_strategy_update(self.strategy_id, event_data)
            except Exception as e:
                logger.error(f"推送策略停止事件失败: {e}")

        except Exception as e:
            logger.error(f"停止网格策略时出错: {e}")

    async def calculate_pnl(self) -> Dict:
        """
        计算网格策略的实时盈亏

        Returns:
            {
                "total_pnl": 总盈亏 (USDT),
                "realized_pnl": 已实现盈亏 (已成交订单的利润),
                "unrealized_pnl": 未实现盈亏 (持仓浮动盈亏),
                "total_fee": 总手续费 (USDT),
                "pnl_rate": 收益率 (%),
                "buy_count": 买入成交次数,
                "sell_count": 卖出成交次数,
                "total_buy_amount": 总买入金额 (USDT),
                "total_sell_amount": 总卖出金额 (USDT),
                "avg_buy_price": 平均买入价格,
                "avg_sell_price": 平均卖出价格,
                "current_position": 当前持仓数量,
                "position_value": 持仓市值 (USDT)
            }
        """
        try:
            from app.core.database import SessionLocal
            from app.models.order import Order as OrderModel
            from sqlalchemy import func

            # 初始化返回数据
            result = {
                "total_pnl": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_fee": 0.0,
                "pnl_rate": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "total_buy_amount": 0.0,
                "total_sell_amount": 0.0,
                "avg_buy_price": 0.0,
                "avg_sell_price": 0.0,
                "current_position": float(self.position_size),
                "position_value": 0.0
            }

            # 从数据库查询该策略的所有订单
            db = SessionLocal()
            try:
                orders = db.query(OrderModel).filter(
                    OrderModel.strategy_id == self.strategy_id
                ).all()

                logger.info(f"[PNL计算] 查询到策略 {self.strategy_id} 的订单总数: {len(orders)}")

                buy_orders = []
                sell_orders = []
                total_fee = Decimal("0")

                # 分类订单并计算手续费
                for order in orders:
                    # 只统计已成交和部分成交的订单
                    # 注意：order.status是枚举类型，需要与枚举值比较
                    from app.models.order import OrderStatus as OS

                    if order.status in [OS.FILLED, OS.PARTIAL_FILLED]:
                        fee = Decimal(str(order.fee or 0))
                        total_fee += fee

                        side = order.side.value if hasattr(order.side, 'value') else str(order.side)

                        if side.lower() == 'buy':
                            buy_orders.append({
                                'price': Decimal(str(order.avg_price or order.price or 0)),
                                'amount': Decimal(str(order.filled_amount or 0)),
                                'fee': fee
                            })
                        elif side.lower() == 'sell':
                            sell_orders.append({
                                'price': Decimal(str(order.avg_price or order.price or 0)),
                                'amount': Decimal(str(order.filled_amount or 0)),
                                'fee': fee
                            })

                # 计算买卖统计
                result['buy_count'] = len(buy_orders)
                result['sell_count'] = len(sell_orders)
                result['total_fee'] = float(total_fee)

                # 计算总买入和卖出金额（用于统计）
                total_buy_amount = sum(o['price'] * o['amount'] for o in buy_orders)
                total_sell_amount = sum(o['price'] * o['amount'] for o in sell_orders)
                total_buy_quantity = sum(o['amount'] for o in buy_orders)
                total_sell_quantity = sum(o['amount'] for o in sell_orders)

                result['total_buy_amount'] = float(total_buy_amount)
                result['total_sell_amount'] = float(total_sell_amount)
                result['avg_buy_price'] = float(total_buy_amount / total_buy_quantity) if total_buy_quantity > 0 else 0.0
                result['avg_sell_price'] = float(total_sell_amount / total_sell_quantity) if total_sell_quantity > 0 else 0.0

                # =================== 使用配对算法计算已实现盈亏 ===================
                # 按时间顺序配对买卖单，只有完整的买卖对才算已实现盈亏
                realized_pnl = Decimal('0')
                paired_count = min(len(buy_orders), len(sell_orders))

                logger.info(f"[PNL计算] 策略 {self.strategy_id}: {len(buy_orders)} 买单, {len(sell_orders)} 卖单, 配对 {paired_count} 对")

                for i in range(paired_count):
                    buy = buy_orders[i]
                    sell = sell_orders[i]

                    buy_cost = buy['price'] * buy['amount']
                    sell_income = sell['price'] * sell['amount']
                    pair_profit = sell_income - buy_cost

                    realized_pnl += pair_profit

                result['realized_pnl'] = float(realized_pnl)

                # 计算未实现盈亏(持仓浮动盈亏)
                # 只计算未配对的买单（持仓部分）
                unpaired_buy_orders = buy_orders[paired_count:]
                unpaired_buy_qty = sum(o['amount'] for o in unpaired_buy_orders)
                unpaired_buy_cost = sum(o['price'] * o['amount'] for o in unpaired_buy_orders)

                # 更新current_position为实际持仓
                result['current_position'] = float(unpaired_buy_qty)

                if unpaired_buy_qty > 0:
                    # 获取当前市场价格
                    try:
                        ticker = await self.exchange.get_ticker(self.symbol)
                        current_price = safe_decimal(ticker.get("last"), 0)

                        # 持仓市值 = 持仓数量 * 当前价格
                        position_value = unpaired_buy_qty * current_price
                        result['position_value'] = float(position_value)

                        # 未实现盈亏 = 持仓市值 - 持仓成本
                        unrealized_pnl = position_value - unpaired_buy_cost
                        result['unrealized_pnl'] = float(unrealized_pnl)

                        logger.info(
                            f"[PNL计算] 未实现盈亏: 持仓{float(unpaired_buy_qty)} {self.symbol.split('-')[0]}, "
                            f"当前价{float(current_price)}, 持仓成本{float(unpaired_buy_cost)} USDT, "
                            f"持仓市值{float(position_value)} USDT, 未实现盈亏{float(unrealized_pnl)} USDT"
                        )
                    except Exception as e:
                        logger.warning(f"获取当前价格失败,无法计算未实现盈亏: {e}")

                # 总盈亏 = 已实现盈亏 + 未实现盈亏
                result['total_pnl'] = result['realized_pnl'] + result['unrealized_pnl']

                # 收益率 = 总盈亏 / 总投入 * 100%
                if result['total_buy_amount'] > 0:
                    result['pnl_rate'] = (result['total_pnl'] / result['total_buy_amount']) * 100

                return result

            finally:
                db.close()

        except Exception as e:
            logger.error(f"计算盈亏失败: {e}")
            return {
                "total_pnl": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_fee": 0.0,
                "pnl_rate": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "total_buy_amount": 0.0,
                "total_sell_amount": 0.0,
                "avg_buy_price": 0.0,
                "avg_sell_price": 0.0,
                "current_position": 0.0,
                "position_value": 0.0
            }
