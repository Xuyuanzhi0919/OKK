"""
波段做多策略 - 永续合约单向做多
适合震荡上涨行情,通过止盈、止损、回调买入实现循环套利
"""
from typing import Dict, Optional
from decimal import Decimal
from loguru import logger
from datetime import datetime
from .base import StrategyBase
from app.services.notification import notification_service


class SwingLongStrategy(StrategyBase):
    """
    波段做多策略

    策略逻辑:
    1. 初始开多头仓位
    2. 价格上涨达到止盈比例 → 平仓止盈
    3. 从最高点回调达到回调比例 → 重新开多
    4. 价格下跌达到止损比例 → 止损平仓

    参数:
    - initial_amount: 初始投入金额(USDT)
    - leverage: 杠杆倍数(1-100x)
    - take_profit_pct: 止盈比例(如5表示5%)
    - stop_loss_pct: 止损比例(如10表示10%)
    - reentry_pct: 回调买入比例(如3表示从最高点回调3%)
    - margin_mode: 保证金模式(isolated/cross)
    """

    def __init__(self, strategy_id: int, exchange, symbol: str, parameters: Dict, user_id: int = 1):
        super().__init__(strategy_id, exchange, symbol, parameters, user_id)

        # 策略名称(用于推送通知)
        self.strategy_name = parameters.get('name', f'波段策略{strategy_id}')

        # 策略参数
        self.initial_amount = Decimal(str(parameters.get("initial_amount", "1000")))
        self.leverage = int(parameters.get("leverage", 5))  # 优化: 默认5x杠杆(降低风险)
        self.take_profit_pct = Decimal(str(parameters.get("take_profit_pct", "15")))  # 优化: 15%止盈
        self.stop_loss_pct = Decimal(str(parameters.get("stop_loss_pct", "5")))  # 优化: 5%止损
        self.reentry_pct = Decimal(str(parameters.get("reentry_pct", "5")))  # 优化: 5%回调
        self.margin_mode = parameters.get("margin_mode", "isolated")

        # 优化参数: 交易过滤
        self.use_limit_orders = parameters.get("use_limit_orders", True)  # 使用限价单
        self.min_volatility = Decimal(str(parameters.get("min_volatility", "3")))  # 最小波动率3%
        self.limit_order_offset_pct = Decimal(str(parameters.get("limit_order_offset_pct", "0.1")))  # 限价单偏移0.1%

        # 状态变量
        self.position = None  # 当前持仓信息 {entry_price, amount, highest_price}
        self.highest_price = Decimal("0")  # 开仓后的最高价格
        self.waiting_reentry = False  # 是否等待回调买入
        self.reentry_trigger_price = Decimal("0")  # 回调买入触发价格
        self.open_position_attempted = False  # 是否已经尝试过开仓

        # 止损恢复机制
        self.stop_loss_count = 0  # 止损次数
        self.max_stop_loss_count = 3  # 最大允许止损次数
        self.cooldown_until = None  # 冷静期结束时间
        self.cooldown_minutes = 10  # 冷静期时长(分钟)
        self.position_scale_ratios = [0.5, 0.25, 0]  # 止损后的仓位比例: 50%, 25%, 0%(停止)

        # 精度参数(启动时从交易所获取)
        self.tick_sz = None  # 价格精度
        self.lot_sz = None  # 数量精度
        self.min_sz = None  # 最小下单量
        self.max_mkt_sz = None  # 市价单最大数量

        logger.info(
            f"波段做多策略初始化: {symbol}, "
            f"投入={self.initial_amount} USDT, "
            f"杠杆={self.leverage}x, "
            f"止盈={self.take_profit_pct}%, "
            f"止损={self.stop_loss_pct}%, "
            f"回调买入={self.reentry_pct}%"
        )

    async def start(self):
        """启动策略"""
        logger.info(f"启动波段做多策略 {self.strategy_id}")
        self.is_running = True

        # 1. 获取交易对精度信息
        try:
            inst_info = await self.exchange.get_instruments(inst_type="SWAP", inst_id=self.symbol)
            if inst_info and len(inst_info) > 0:
                instrument = inst_info[0]
                self.tick_sz = Decimal(instrument.get("tickSz", "0.01"))
                self.lot_sz = Decimal(instrument.get("lotSz", "1"))
                self.min_sz = Decimal(instrument.get("minSz", "0.001"))
                self.max_mkt_sz = Decimal(instrument.get("maxMktSz", "1000000"))  # 市价单最大数量
                self.ct_val = Decimal(instrument.get("ctVal", "1"))  # 合约面值: 1张 = ct_val个币
                logger.info(f"交易对精度: tickSz={self.tick_sz}, lotSz={self.lot_sz}, minSz={self.min_sz}, maxMktSz={self.max_mkt_sz}, ctVal={self.ct_val}")
        except Exception as e:
            logger.error(f"获取交易对信息失败: {e}")
            self.tick_sz = Decimal("0.01")
            self.lot_sz = Decimal("1")
            self.min_sz = Decimal("0.001")
            self.max_mkt_sz = Decimal("10000")  # 默认最大值
            self.ct_val = Decimal("1")  # 默认面值

        # 2. 设置杠杆
        if self.symbol.endswith("-SWAP") or self.symbol.endswith("-FUTURES"):
            try:
                margin_mode_cn = "逐仓" if self.margin_mode == "isolated" else "全仓"
                logger.info(f"为 {self.symbol} 设置杠杆倍数: {self.leverage}x ({margin_mode_cn}模式)")

                leverage_result = await self.exchange.set_leverage(
                    lever=str(self.leverage),
                    mgn_mode=self.margin_mode,
                    inst_id=self.symbol,
                    pos_side="net"
                )
                logger.info(f"杠杆倍数设置成功: {leverage_result}")
            except Exception as e:
                logger.warning(f"设置杠杆倍数失败(可能已设置): {e}")

        # 3. 清理未成交订单
        await self._cancel_pending_orders()

        # 4. 检查是否已有持仓
        await self._check_existing_position()

        # 5. 如果没有持仓,标记需要开仓(在on_tick中执行)
        # 不立即开仓,避免与手动开仓冲突
        if not self.position:
            logger.info("启动时未检测到持仓,将在监控中尝试开仓")
            self.open_position_attempted = False  # 允许后续开仓
        else:
            logger.info(f"检测到已有持仓,继续监控: {self.position}")
            self.open_position_attempted = True  # 已有持仓,不再尝试开仓

    async def stop(self, cancel_orders: bool = False):
        """停止策略"""
        logger.info(f"停止波段做多策略 {self.strategy_id}")
        self.is_running = False

        # 停止时平仓所有持仓(波段策略建议停止时平仓)
        if self.position:
            logger.info(f"策略停止,平仓当前持仓: {self.position['amount']}")
            await self._close_position("策略停止,平仓")

    async def on_tick(self, ticker: Dict):
        """
        处理实时行情

        Args:
            ticker: {"last": "3200.5", "askPx": "3200.6", "bidPx": "3200.4"}
        """
        if not self.is_running:
            return

        try:
            current_price = Decimal(str(ticker.get("last", 0)))
            if current_price <= 0:
                return

            # 【新增】健康检查日志 - 每60次tick(约5分钟)打印一次状态
            if not hasattr(self, '_health_check_count'):
                self._health_check_count = 0

            self._health_check_count += 1
            if self._health_check_count >= 60:
                self._health_check_count = 0
                logger.info(
                    f"💊 策略健康检查 [{self.symbol}] "
                    f"价格={current_price:.6f} | "
                    f"持仓={'有' if self.position else '无'} | "
                    f"等待回调={'是' if self.waiting_reentry else '否'} | "
                    f"已尝试开仓={'是' if self.open_position_attempted else '否'} | "
                    f"冷静期={'有' if self.cooldown_until else '无'} | "
                    f"止损次数={self.stop_loss_count}/{self.max_stop_loss_count}"
                )

            # 检查是否在冷静期
            if self.cooldown_until:
                from datetime import datetime
                now = datetime.now()
                if now < self.cooldown_until:
                    # 仍在冷静期,不做任何操作
                    return
                else:
                    # 冷静期结束
                    logger.info(f"✅ 冷静期结束,恢复交易监控")
                    self.cooldown_until = None

            # 定期检查持仓状态(每10次tick检查一次,避免频繁API调用)
            # 这样可以检测到手动开仓或策略启动后开的仓
            if not hasattr(self, '_tick_count'):
                self._tick_count = 0

            self._tick_count += 1
            if self._tick_count >= 10:
                self._tick_count = 0
                # 【改进】检查持仓前记录当前状态,用于后续对比
                had_position_before = self.position is not None
                await self._check_existing_position()

                # 【新增】状态自检: 如果开仓标志=True但实际无持仓,可能是订单被撤销但未感知
                if self.open_position_attempted and not self.position and not had_position_before:
                    logger.warning(
                        "⚠️  状态异常检测: open_position_attempted=True 但无持仓, "
                        "可能是订单被撤销, 重置标志"
                    )
                    self.open_position_attempted = False

            # 如果有持仓,监控止盈止损
            if self.position:
                await self._monitor_position(current_price)

            # 如果在等待回调买入,监控回调
            elif self.waiting_reentry:
                await self._monitor_reentry(current_price)

            # 如果既没有持仓也不在等待回调,且未尝试过开仓,则尝试开仓
            elif not self.position and not self.waiting_reentry and not self.open_position_attempted:
                logger.info("检测到无持仓且未等待回调,尝试开仓")
                self.open_position_attempted = True  # 标记已尝试
                await self._open_long_position()

        except Exception as e:
            logger.error(f"处理tick数据失败: {e}")

    async def on_kline(self, kline: Dict):
        """处理K线数据(可选,本策略主要使用tick)"""
        pass

    async def on_order_update(self, order: Dict):
        """
        处理订单更新

        Args:
            order: 订单更新信息
        """
        order_id = order.get('ordId')
        state = order.get('state')
        side = order.get('side')

        logger.info(f"📮 订单更新: {order_id} - {state} ({side})")

        # 处理订单成交
        if state == "filled":
            logger.success(f"✅ 订单已成交: {order_id} - {side}")
            # 立即检查持仓状态
            await self._check_existing_position()

        # 【关键修复】处理订单撤销
        elif state == "canceled":
            logger.warning(f"⚠️  订单已撤销: {order_id} - {side}")

            # 如果是开仓订单被撤销,重置标志允许重新尝试
            if side == "buy":
                logger.info("买入订单被撤销,重置开仓标志,允许重新尝试")
                self.open_position_attempted = False
                # 设置1分钟冷静期,避免立即重试
                from datetime import datetime, timedelta
                self.cooldown_until = datetime.now() + timedelta(minutes=1)
                logger.info(f"⏸️  设置1分钟冷静期,到 {self.cooldown_until.strftime('%H:%M:%S')}")

            # 如果是平仓订单被撤销,重新检查持仓状态
            elif side == "sell":
                logger.warning("卖出订单被撤销,可能仍有持仓,重新检查")
                await self._check_existing_position()

        # 处理部分成交
        elif state == "partially_filled":
            logger.info(f"订单部分成交: {order_id} - {order.get('accFillSz')}/{order.get('sz')}")
            # 部分成交也可能产生持仓,检查一下
            await self._check_existing_position()

    async def _check_existing_position(self):
        """检查现有持仓"""
        try:
            positions = await self.exchange.get_positions(inst_type="SWAP", inst_id=self.symbol)

            if positions and len(positions) > 0:
                pos = positions[0]
                pos_amount = Decimal(str(pos.get("pos", 0)))

                # 只检测多头持仓(pos > 0)
                if pos_amount > 0:
                    avg_price = Decimal(str(pos.get("avgPx", 0)))

                    # 如果已经有持仓记录,只更新数量和均价
                    if self.position:
                        self.position["entry_price"] = avg_price
                        self.position["amount"] = pos_amount
                        # 保持原有的highest_price,因为这是策略运行期间跟踪的
                        if avg_price > self.highest_price:
                            self.highest_price = avg_price
                            self.position["highest_price"] = avg_price
                        logger.debug(f"更新持仓: {pos_amount} @ {avg_price}")
                    else:
                        # 首次检测到持仓,创建持仓记录
                        self.position = {
                            "entry_price": avg_price,
                            "amount": pos_amount,
                            "contract_amount": pos_amount,  # 合约张数
                            "highest_price": avg_price
                        }
                        self.highest_price = avg_price
                        self.waiting_reentry = False
                        self.open_position_attempted = False  # 有持仓后重置,允许下次止盈平仓后重新开仓
                        logger.info(f"🔍 检测到已有持仓: {pos_amount}张 @ {avg_price}")
                else:
                    # 没有多头持仓
                    if self.position:
                        logger.info("持仓已平仓,清除持仓记录")
                    self.position = None
            else:
                # 没有任何持仓
                if self.position:
                    logger.info("持仓已平仓,清除持仓记录")
                self.position = None

        except Exception as e:
            logger.error(f"检查持仓失败: {e}")

    async def _cancel_pending_orders(self):
        """取消当前交易对的所有未成交订单"""
        try:
            logger.info(f"🔍 检查 {self.symbol} 的未成交订单...")

            # 获取未成交订单
            pending_orders = await self.exchange.get_orders_pending(
                inst_type="SWAP",
                inst_id=self.symbol
            )

            if not pending_orders:
                logger.info("✅ 没有未成交订单")
                return

            logger.warning(f"⚠️  发现 {len(pending_orders)} 笔未成交订单,开始自动撤销...")

            # 取消每笔订单
            canceled_count = 0
            failed_count = 0

            for order in pending_orders:
                order_id = order.get("ordId")
                side = order.get("side")
                size = order.get("sz")
                order_type = order.get("ordType")
                state = order.get("state")

                logger.info(f"📋 订单: {side} {size}张 {order_type} - 状态: {state} - ID: {order_id}")

                try:
                    # 取消订单
                    result = await self.exchange.cancel_order(
                        symbol=self.symbol,
                        order_id=order_id
                    )

                    logger.success(f"✅ 已取消订单: {order_id}")
                    canceled_count += 1

                except Exception as cancel_error:
                    logger.error(f"❌ 取消订单 {order_id} 失败: {cancel_error}")
                    failed_count += 1

            # 总结
            if canceled_count > 0:
                logger.success(f"✅ 成功撤销 {canceled_count} 笔订单")
            if failed_count > 0:
                logger.warning(f"⚠️  {failed_count} 笔订单撤销失败")

        except Exception as e:
            logger.error(f"❌ 撤销未成交订单异常: {e}")

    async def _check_volatility(self) -> bool:
        """
        检查波动率是否足够

        Returns:
            bool: True=波动率足够, False=波动率不足
        """
        try:
            ticker = await self.exchange.get_ticker(self.symbol)
            open24h = Decimal(str(ticker.get("open24h", 0)))
            high24h = Decimal(str(ticker.get("high24h", 0)))
            low24h = Decimal(str(ticker.get("low24h", 0)))

            if open24h <= 0:
                logger.warning("无法获取24h数据,跳过波动率检查")
                return True

            # 计算24h波动率: (最高价-最低价) / 开盘价 * 100
            volatility_pct = (high24h - low24h) / open24h * 100

            if volatility_pct < self.min_volatility:
                logger.info(f"⏸️  波动率不足: {volatility_pct:.2f}% < {self.min_volatility}%, 跳过开仓")
                return False

            logger.debug(f"✅ 波动率检查通过: {volatility_pct:.2f}%")
            return True

        except Exception as e:
            logger.error(f"波动率检查失败: {e}")
            return True  # 检查失败时允许交易

    async def _open_long_position(self):
        """开多头仓位"""
        try:
            # 1. 检查并撤销未成交订单(避免重复开仓)
            await self._cancel_pending_orders()

            # 2. 优化: 检查波动率
            if not await self._check_volatility():
                logger.info("波动率不足,跳过开仓")
                return

            # 3. 获取当前价格
            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = Decimal(str(ticker.get("last", 0)))

            if current_price <= 0:
                logger.error("无法获取当前价格,开仓失败")
                return

            # 根据止损次数调整仓位大小
            position_ratio = Decimal("1.0")  # 默认100%仓位
            if self.stop_loss_count > 0 and self.stop_loss_count <= len(self.position_scale_ratios):
                position_ratio = Decimal(str(self.position_scale_ratios[self.stop_loss_count - 1]))
                logger.info(f"📊 根据第{self.stop_loss_count}次止损,调整仓位为 {position_ratio*100:.0f}%")

            # 如果仓位比例为0,则不开仓
            if position_ratio <= 0:
                logger.warning("仓位比例为0,跳过开仓")
                return

            # 计算开仓数量(币的数量): coin_amount = (本金 * 仓位比例 * 杠杆) / 价格
            coin_amount = (self.initial_amount * position_ratio * self.leverage) / current_price

            # 转换为合约张数: contract_amount = 币数量 / 合约面值
            # 对于DOGE-USDT-SWAP: ct_val=1000, 即1张=1000DOGE
            contract_amount = coin_amount / self.ct_val

            # 向下取整到lot_sz (合约张数的最小单位)
            contract_amount = (contract_amount // self.lot_sz) * self.lot_sz

            if contract_amount < self.min_sz:
                logger.error(f"开仓数量 {contract_amount} 张 (={contract_amount * self.ct_val} 币) 小于最小下单量 {self.min_sz} 张")
                return

            # 限制在市价单最大数量内 (max_mkt_sz是合约张数)
            if contract_amount > self.max_mkt_sz:
                logger.warning(f"开仓数量 {contract_amount} 张超过市价单最大限制 {self.max_mkt_sz} 张，将限制为最大值")
                contract_amount = self.max_mkt_sz

            # 计算实际买入的币数量
            actual_coin_amount = contract_amount * self.ct_val

            # 优化: 使用限价单或市价单开仓
            # 对于低价币种(价格<0.0001),限价单可能因精度问题被撤销,使用市价单更可靠
            should_use_limit = self.use_limit_orders and current_price >= Decimal("0.0001")

            if should_use_limit:
                # 计算限价单价格(买入时略低于当前价,以更好的价格成交)
                limit_price = current_price * (Decimal("1") - self.limit_order_offset_pct / Decimal("100"))
                # 向下取整到价格精度
                limit_price = (limit_price // self.tick_sz) * self.tick_sz

                # 检查限价是否有效(必须至少偏离一个tickSz)
                if limit_price >= current_price:
                    logger.warning(f"⚠️  限价 {limit_price} 未低于市价 {current_price},改用市价单")
                    should_use_limit = False
                elif (current_price - limit_price) < self.tick_sz:
                    logger.warning(f"⚠️  限价偏移 {current_price - limit_price} 小于tickSz {self.tick_sz},改用市价单")
                    should_use_limit = False

            if should_use_limit:
                logger.info(f"🎯 使用限价单开多: {contract_amount} 张 (={actual_coin_amount} 币) @ {limit_price} (偏移{self.limit_order_offset_pct}%)")

                order = await self.exchange.create_order(
                    symbol=self.symbol,
                    side="buy",
                    order_type="post_only",  # Maker订单,享受更低手续费(0.02%)
                    amount=float(contract_amount),
                    price=float(limit_price),
                    td_mode=self.margin_mode,
                    pos_side="net"
                )

                order_type_str = "post_only"
                order_price = limit_price
            else:
                # 使用市价单
                logger.info(f"开多头仓位: {contract_amount} 张 (={actual_coin_amount} 币) @ 市价 (预计约 {current_price})")

                order = await self.exchange.create_order(
                    symbol=self.symbol,
                    side="buy",
                    order_type="market",
                    amount=float(contract_amount),
                    td_mode=self.margin_mode,
                    pos_side="net"
                )

                order_type_str = "market"
                order_price = None

            if order and order.get("ordId"):
                logger.info(f"✅ 开仓订单提交成功: {order.get('ordId')}")

                # 保存订单到数据库
                await self._save_order_to_db(
                    order_data=order,
                    side="buy",
                    order_type=order_type_str,
                    price=float(order_price) if order_price else None,
                    amount=contract_amount
                )

                # 发送开仓通知
                try:
                    margin = float(self.initial_amount) / self.leverage
                    await notification_service.notify_position_opened(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        strategy_name=self.strategy_name,
                        symbol=self.symbol,
                        side="buy",
                        # 使用下单时的价格作为通知的入场价格
                        entry_price=float(order_price if order_price else current_price),
                        amount=float(contract_amount),
                        leverage=self.leverage,
                        margin=margin
                    )
                except Exception as e:
                    logger.error(f"发送开仓通知失败: {e}")

                # 重要: 不要立即设置self.position
                # 等待订单实际成交后,通过_check_existing_position()检测到真实持仓再设置
                # 这样可以避免订单未成交导致的重复开仓问题
                logger.info(f"⏳ 等待订单成交,将在下次检查持仓时更新策略状态")

                # 标记已尝试开仓,避免重复提交订单
                # 但不设置position,等实际成交后再设置
                self.open_position_attempted = True
            else:
                logger.error(f"❌ 开仓失败: {order}")
                # 开仓失败,等待一段时间后重试
                # 设置一个短暂的冷静期(1分钟),避免立即重试
                from datetime import datetime, timedelta
                self.cooldown_until = datetime.now() + timedelta(minutes=1)
                logger.warning(f"⏸️  开仓失败,等待1分钟后重试")
                self.open_position_attempted = False  # 重置标志,允许重试

        except Exception as e:
            logger.error(f"开仓异常: {e}")

    async def _close_position(self, reason: str):
        """平仓"""
        if not self.position:
            return

        try:
            # 获取合约张数(如果没有则用币数量除以合约面值)
            contract_amount = self.position.get("contract_amount")
            if not contract_amount:
                coin_amount = self.position["amount"]
                contract_amount = coin_amount / self.ct_val

            # 获取当前价格用于限价单
            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = Decimal(str(ticker.get("last", 0)))

            # 判断是否是止损
            is_stop_loss = "止损" in reason

            # 优化: 使用限价单或市价单平仓
            # 止损时优先使用市价单,确保立即成交
            # 止盈时可以使用限价单,争取更好价格
            # 对于低价币种(价格<0.0001),限价单可能因精度问题被撤销,使用市价单更可靠
            should_use_limit = (
                self.use_limit_orders and
                not is_stop_loss and  # 止损时不用限价单
                current_price > 0 and
                current_price >= Decimal("0.0001")
            )

            if should_use_limit:
                # 计算限价单价格(卖出时略高于当前价,以更好的价格成交)
                limit_price = current_price * (Decimal("1") + self.limit_order_offset_pct / Decimal("100"))
                # 向上取整到价格精度
                limit_price = ((limit_price // self.tick_sz) + Decimal("1")) * self.tick_sz

                # 检查限价是否有效(必须至少偏离一个tickSz)
                if limit_price <= current_price:
                    logger.warning(f"⚠️  限价 {limit_price} 未高于市价 {current_price},改用市价单")
                    should_use_limit = False
                elif (limit_price - current_price) < self.tick_sz:
                    logger.warning(f"⚠️  限价偏移 {limit_price - current_price} 小于tickSz {self.tick_sz},改用市价单")
                    should_use_limit = False

            if should_use_limit:
                logger.info(f"🎯 使用限价单平仓: {contract_amount} 张 (={contract_amount * self.ct_val} 币) @ {limit_price} - 原因: {reason}")

                order = await self.exchange.create_order(
                    symbol=self.symbol,
                    side="sell",
                    order_type="post_only",  # Maker订单,享受更低手续费(0.02%)
                    amount=float(contract_amount),
                    price=float(limit_price),
                    td_mode=self.margin_mode,
                    pos_side="net",
                    reduce_only=True
                )

                order_type_str = "post_only"
                order_price = limit_price
            else:
                # 使用市价单
                logger.info(f"平仓: {contract_amount} 张 (={contract_amount * self.ct_val} 币) - 原因: {reason}")

                order = await self.exchange.create_order(
                    symbol=self.symbol,
                    side="sell",
                    order_type="market",
                    amount=float(contract_amount),
                    td_mode=self.margin_mode,
                    pos_side="net",
                    reduce_only=True
                )

                order_type_str = "market"
                order_price = None

            if order and order.get("ordId"):
                logger.info(f"✅ 平仓订单提交成功: {order.get('ordId')}")

                # 保存订单到数据库
                await self._save_order_to_db(
                    order_data=order,
                    side="sell",
                    order_type=order_type_str,
                    price=float(order_price) if order_price else None,
                    amount=contract_amount
                )

                # 发送平仓通知
                try:
                    entry_price = self.position["entry_price"]
                    coin_amount = self.position.get("amount", contract_amount * self.ct_val)
                    pnl = (current_price - entry_price) * coin_amount * self.leverage
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100 * self.leverage

                    await notification_service.notify_position_closed(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        strategy_name=self.strategy_name,
                        symbol=self.symbol,
                        side="buy",
                        entry_price=float(entry_price),
                        exit_price=float(current_price),
                        amount=float(coin_amount),
                        pnl=float(pnl),
                        pnl_pct=float(pnl_pct),
                        reason=reason
                    )
                except Exception as e:
                    logger.error(f"发送平仓通知失败: {e}")

                # 清空持仓
                self.position = None
                self.highest_price = Decimal("0")
            else:
                logger.error(f"❌ 平仓失败: {order}")

        except Exception as e:
            logger.error(f"❌ 平仓异常: {e}")

    async def _monitor_position(self, current_price: Decimal):
        """监控持仓,检查止盈止损"""
        if not self.position:
            return

        entry_price = self.position["entry_price"]

        # 更新最高价
        if current_price > self.highest_price:
            self.highest_price = current_price
            self.position["highest_price"] = current_price

        # 计算币价变化率
        price_change_pct = (current_price - entry_price) / entry_price * 100

        # 新逻辑: 直接使用币价变化率进行判断
        # self.take_profit_pct 现在代表币价变化的百分比

        # 检查止盈 (基于币价变化率)
        if price_change_pct >= self.take_profit_pct:
            logger.info(f"触发止盈: 当前价 {current_price}, 开仓价 {entry_price}, 币价变化 {price_change_pct:.2f}%")
            await self._close_position(f"止盈 {price_change_pct:.2f}%")

            # 止盈成功,重置止损次数(说明策略运行良好)
            if self.stop_loss_count > 0:
                logger.info(f"✅ 止盈成功,重置止损次数 ({self.stop_loss_count} → 0)")
                self.stop_loss_count = 0

            # 设置回调买入监控
            self.waiting_reentry = True
            self.reentry_trigger_price = self.highest_price * (1 - self.reentry_pct / 100)
            logger.info(f"等待回调买入,触发价格: {self.reentry_trigger_price}")
            return

        # 检查止损 (基于币价变化率)
        if price_change_pct <= -self.stop_loss_pct:
            logger.warning(f"触发止损: 当前价 {current_price}, 开仓价 {entry_price}, 币价变化 {price_change_pct:.2f}%")
            await self._close_position(f"止损 {price_change_pct:.2f}%")

            # 增加止损次数
            self.stop_loss_count += 1
            logger.warning(f"⚠️  第 {self.stop_loss_count} 次止损 (最大允许 {self.max_stop_loss_count} 次)")

            # 设置冷静期
            from datetime import datetime, timedelta
            self.cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
            logger.info(f"🕐 进入冷静期,持续 {self.cooldown_minutes} 分钟,到 {self.cooldown_until.strftime('%H:%M:%S')}")

            # 根据止损次数决定后续操作
            if self.stop_loss_count >= self.max_stop_loss_count:
                logger.error(f"❌ 达到最大止损次数 {self.max_stop_loss_count},策略停止交易,等待人工介入")

                # 发送风险预警通知
                try:
                    await notification_service.notify_risk_warning(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        strategy_name=self.strategy_name,
                        symbol=self.symbol,
                        warning_type="max_stop_loss",
                        message_text=f"达到最大止损次数({self.max_stop_loss_count}次),策略已停止",
                        data={
                            "stop_loss_count": self.stop_loss_count,
                            "max_stop_loss_count": self.max_stop_loss_count
                        }
                    )
                except Exception as e:
                    logger.error(f"发送风险预警失败: {e}")

                self.waiting_reentry = False
                self.open_position_attempted = True  # 阻止自动开仓
            else:
                # 还可以继续交易,冷静期后以降低的仓位重新开仓
                position_ratio = self.position_scale_ratios[self.stop_loss_count - 1]
                logger.info(f"📊 冷静期后将以 {position_ratio*100:.0f}% 仓位重新开仓")
                self.waiting_reentry = True  # 标记为等待重新入场
                self.open_position_attempted = False  # 允许重新开仓

            return

    async def _monitor_reentry(self, current_price: Decimal):
        """监控回调买入"""
        if not self.waiting_reentry:
            return

        # 价格回调到触发价格以下,重新开多
        if current_price <= self.reentry_trigger_price:
            logger.info(f"触发回调买入: 当前价格 {current_price}, 触发价 {self.reentry_trigger_price}")
            await self._open_long_position()

    async def calculate_pnl(self) -> Dict:
        """
        计算波段做多策略的实时盈亏

        Returns:
            盈亏统计数据
        """
        try:
            from app.core.database import SessionLocal
            from app.models.order import Order as OrderModel, OrderStatus

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
                "current_position": 0.0,
                "position_value": 0.0
            }

            # 从数据库查询订单
            db = SessionLocal()
            try:
                orders = db.query(OrderModel).filter(
                    OrderModel.strategy_id == self.strategy_id
                ).all()

                buy_total = Decimal("0")
                sell_total = Decimal("0")
                buy_amount_sum = Decimal("0")
                sell_amount_sum = Decimal("0")
                total_fee = Decimal("0")

                for order in orders:
                    if order.status in [OrderStatus.FILLED, OrderStatus.PARTIAL_FILLED]:
                        fee = Decimal(str(order.fee or 0))
                        total_fee += fee

                        price = Decimal(str(order.avg_price or order.price or 0))
                        amount = Decimal(str(order.filled_amount or 0))

                        side = order.side.value if hasattr(order.side, 'value') else str(order.side)

                        if side.lower() == 'buy':
                            result["buy_count"] += 1
                            buy_total += price * amount
                            buy_amount_sum += amount
                        elif side.lower() == 'sell':
                            result["sell_count"] += 1
                            sell_total += price * amount
                            sell_amount_sum += amount

                # 计算平均价格
                if buy_amount_sum > 0:
                    result["avg_buy_price"] = float(buy_total / buy_amount_sum)
                    result["total_buy_amount"] = float(buy_total)

                if sell_amount_sum > 0:
                    result["avg_sell_price"] = float(sell_total / sell_amount_sum)
                    result["total_sell_amount"] = float(sell_total)

                # 已实现盈亏 = 卖出总额 - 买入总额 - 手续费
                result["realized_pnl"] = float(sell_total - buy_total - total_fee)
                result["total_fee"] = float(total_fee)

                # 未实现盈亏(当前持仓)
                # 优先从交易所获取真实持仓数据
                try:
                    positions = await self.exchange.get_positions(inst_type="SWAP", inst_id=self.symbol)
                    if positions and len(positions) > 0:
                        pos = positions[0]
                        pos_size = Decimal(str(pos.get("pos", 0)))

                        if pos_size != 0:
                            # OKX直接返回未实现盈亏(USDT)
                            unrealized_pnl = Decimal(str(pos.get("upl", 0)))
                            avg_px = Decimal(str(pos.get("avgPx", 0)))
                            mark_px = Decimal(str(pos.get("markPx", 0)))

                            result["current_position"] = abs(float(pos_size))
                            result["position_value"] = float(mark_px * abs(pos_size) * self.ct_val)
                            result["unrealized_pnl"] = float(unrealized_pnl)

                            logger.info(f"从交易所获取持仓盈亏: 持仓={pos_size}张, 开仓价={avg_px}, 当前价={mark_px}, 未实现盈亏={unrealized_pnl} USDT")
                        else:
                            # 无持仓但策略有持仓记录,使用策略记录计算
                            if self.position:
                                ticker = await self.exchange.get_ticker(self.symbol)
                                current_price = Decimal(str(ticker.get("last", 0)))
                                contract_amount = self.position.get("contract_amount", 0)
                                entry_price = self.position.get("entry_price", 0)

                                # 未实现盈亏 = (当前价 - 开仓价) × 合约张数 × 合约面值
                                result["current_position"] = float(contract_amount)
                                result["position_value"] = float(current_price * Decimal(str(contract_amount)) * self.ct_val)
                                result["unrealized_pnl"] = float(
                                    (current_price - Decimal(str(entry_price))) * Decimal(str(contract_amount)) * self.ct_val
                                )
                    elif self.position:
                        # 交易所查询失败,使用策略记录计算
                        ticker = await self.exchange.get_ticker(self.symbol)
                        current_price = Decimal(str(ticker.get("last", 0)))
                        contract_amount = self.position.get("contract_amount", 0)
                        entry_price = self.position.get("entry_price", 0)

                        result["current_position"] = float(contract_amount)
                        result["position_value"] = float(current_price * Decimal(str(contract_amount)) * self.ct_val)
                        result["unrealized_pnl"] = float(
                            (current_price - Decimal(str(entry_price))) * Decimal(str(contract_amount)) * self.ct_val
                        )
                except Exception as pos_error:
                    logger.warning(f"获取持仓失败,使用策略记录计算: {pos_error}")
                    if self.position:
                        ticker = await self.exchange.get_ticker(self.symbol)
                        current_price = Decimal(str(ticker.get("last", 0)))
                        contract_amount = self.position.get("contract_amount", 0)
                        entry_price = self.position.get("entry_price", 0)

                        result["current_position"] = float(contract_amount)
                        result["position_value"] = float(current_price * Decimal(str(contract_amount)) * self.ct_val)
                        result["unrealized_pnl"] = float(
                            (current_price - Decimal(str(entry_price))) * Decimal(str(contract_amount)) * self.ct_val
                        )

                # 总盈亏 = 已实现 + 未实现
                result["total_pnl"] = result["realized_pnl"] + result["unrealized_pnl"]

                # 收益率
                if self.initial_amount > 0:
                    result["pnl_rate"] = (result["total_pnl"] / float(self.initial_amount)) * 100

            finally:
                db.close()

            return result

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
