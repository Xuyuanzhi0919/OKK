"""
波段做空策略 - 永续合约单向做空
适合震荡下跌行情,通过止盈、止损、反弹卖出实现循环套利
"""
import asyncio
from typing import Dict, Optional
from decimal import Decimal
from loguru import logger
from datetime import datetime, timedelta
from .base import StrategyBase
from app.services.notification import notification_service


class SwingShortStrategy(StrategyBase):
    """
    波段做空策略

    策略逻辑:
    1. 初始开空头仓位
    2. 价格下跌达到止盈比例 → 平仓止盈
    3. 从最低点反弹达到反弹比例 → 重新开空
    4. 价格上涨达到止损比例 → 止损平仓

    参数:
    - initial_amount: 初始投入金额(USDT)
    - leverage: 杠杆倍数(1-100x)
    - take_profit_pct: 止盈比例(如5表示5%)
    - stop_loss_pct: 止损比例(如10表示10%)
    - reentry_pct: 反弹卖出比例(如3表示从最低点反弹3%)
    - margin_mode: 保证金模式(isolated/cross)
    """

    def __init__(self, strategy_id: int, exchange, symbol: str, parameters: Dict, user_id: int = 1):
        super().__init__(strategy_id, exchange, symbol, parameters, user_id)

        # 策略名称(用于推送通知)
        self.strategy_name = parameters.get('name', f'波段做空策略{strategy_id}')

        # 策略参数
        self.initial_amount = Decimal(str(parameters.get("initial_amount", "1000")))
        self.leverage = int(parameters.get("leverage", 5))
        self.take_profit_pct = Decimal(str(parameters.get("take_profit_pct", "15")))
        self.stop_loss_pct = Decimal(str(parameters.get("stop_loss_pct", "5")))
        self.reentry_pct = Decimal(str(parameters.get("reentry_pct", "5")))
        self.margin_mode = parameters.get("margin_mode", "isolated")

        # 优化参数: 交易过滤
        self.use_limit_orders = parameters.get("use_limit_orders", True)
        self.min_volatility = Decimal(str(parameters.get("min_volatility", "3")))
        # 增加默认偏移量到0.5%，避免post_only被拒绝
        self.limit_order_offset_pct = Decimal(str(parameters.get("limit_order_offset_pct", "0.5")))

        # 【新增】追踪止损参数
        self.enable_trailing_stop = parameters.get("enable_trailing_stop", False)  # 是否启用追踪止损
        self.trailing_stop_pct = Decimal(str(parameters.get("trailing_stop_pct", "2")))  # 追踪止损回调比例
        self.trailing_stop_activation_pct = Decimal(str(parameters.get("trailing_stop_activation_pct", "3")))  # 激活追踪止损的盈利比例

        # 状态变量
        self.position = None  # 当前持仓信息 {entry_price, amount, lowest_price}
        self.lowest_price = Decimal("9999999")  # 开仓后的最低价格
        self.highest_trailing_price = Decimal("0")  # 追踪止损的最高触发价
        self.trailing_stop_triggered = False  # 是否已激活追踪止损
        self.waiting_reentry = False  # 是否等待反弹卖出
        self.reentry_trigger_price = Decimal("0")  # 反弹卖出触发价格
        self.open_position_attempted = False  # 是否已经尝试过开仓

        # 止损恢复机制
        self.stop_loss_count = 0
        self.max_stop_loss_count = 3
        self.cooldown_until = None
        self.cooldown_minutes = 10
        self.position_scale_ratios = [0.5, 0.25, 0]

        # 精度参数(启动时从交易所获取)
        self.tick_sz = None
        self.lot_sz = None
        self.min_sz = None
        self.max_mkt_sz = None

        logger.info(
            f"波段做空策略初始化: {symbol}, "
            f"投入={self.initial_amount} USDT, "
            f"杠杆={self.leverage}x, "
            f"止盈={self.take_profit_pct}%, "
            f"止损={self.stop_loss_pct}%, "
            f"反弹卖出={self.reentry_pct}%"
        )

    async def start(self):
        """启动策略"""
        logger.info(f"启动波段做空策略 {self.strategy_id}")
        self.is_running = True

        # 保存是否为模拟盘，模拟盘订单簿薄，直接用市价单
        self.is_simulated = getattr(self.exchange, 'simulated', False)
        logger.info(f"交易模式: {'模拟盘' if self.is_simulated else '实盘'}")

        try:
            inst_info = await self.exchange.get_instruments(inst_type="SWAP", inst_id=self.symbol)
            if inst_info and len(inst_info) > 0:
                instrument = inst_info[0]
                self.tick_sz = Decimal(instrument.get("tickSz", "0.01"))
                self.lot_sz = Decimal(instrument.get("lotSz", "1"))
                self.min_sz = Decimal(instrument.get("minSz", "0.001"))
                self.max_mkt_sz = Decimal(instrument.get("maxMktSz", "1000000"))
                self.ct_val = Decimal(instrument.get("ctVal", "1"))
                logger.info(f"交易对精度: tickSz={self.tick_sz}, lotSz={self.lot_sz}, minSz={self.min_sz}, maxMktSz={self.max_mkt_sz}, ctVal={self.ct_val}")
        except Exception as e:
            logger.error(f"获取交易对信息失败: {e}")
            self.tick_sz = Decimal("0.01")
            self.lot_sz = Decimal("1")
            self.min_sz = Decimal("0.001")
            self.max_mkt_sz = Decimal("10000")
            self.ct_val = Decimal("1")

        if self.symbol.endswith("-SWAP") or self.symbol.endswith("-FUTURES"):
            try:
                margin_mode_cn = "逐仓" if self.margin_mode == "isolated" else "全仓"
                logger.info(f"为 {self.symbol} 设置杠杆倍数: {self.leverage}x ({margin_mode_cn}模式)")
                leverage_result = await self.exchange.set_leverage(
                    lever=str(self.leverage), mgn_mode=self.margin_mode, inst_id=self.symbol, pos_side="net"
                )
                logger.info(f"杠杆倍数设置成功: {leverage_result}")
            except Exception as e:
                logger.warning(f"设置杠杆倍数失败(可能已设置): {e}")

        # 【关键修复】启动时先检查并清理异常订单
        await self._cancel_pending_orders()

        # 等待一小段时间确保订单取消完成
        await asyncio.sleep(0.5)

        # 再次检查，如果仍有未成交订单，记录警告
        pending_orders = await self.exchange.get_orders_pending(
            inst_type="SWAP", inst_id=self.symbol
        )
        if pending_orders:
            logger.warning(f"⚠️  启动时仍有{len(pending_orders)}笔未成交订单未清理")
            for order in pending_orders:
                logger.info(f"  - {order.get('side')} {order.get('sz')}张 @ {order.get('px')} ID:{order.get('ordId')}")

        await self._check_existing_position()

        # 验证本地持仓与交易所一致
        if self.position:
            # 本地检测到持仓，向交易所确认
            positions = await self.exchange.get_positions(inst_type="SWAP", inst_id=self.symbol)
            has_real_position = False
            if positions and len(positions) > 0:
                pos = positions[0]
                pos_amount = Decimal(str(pos.get("pos", 0)))
                if pos_amount < 0:
                    has_real_position = True

            if not has_real_position:
                logger.warning("⚠️  启动检测: 本地有持仓记录但交易所无持仓，清除本地状态")
                self.position = None
                self.open_position_attempted = False

        if not self.position:
            logger.info("启动时未检测到持仓,将在监控中尝试开仓")
            self.open_position_attempted = False
        else:
            logger.info(f"检测到已有持仓,继续监控: {self.position}")
            self.open_position_attempted = True

    async def stop(self, cancel_orders: bool = False):
        """停止策略"""
        logger.info(f"停止波段做空策略 {self.strategy_id}")
        self.is_running = False
        if self.position:
            logger.info(f"策略停止,平仓当前持仓: {self.position['amount']}")
            await self._close_position("策略停止,平仓")

    async def on_tick(self, ticker: Dict):
        if not self.is_running:
            return

        try:
            current_price = Decimal(str(ticker.get("last", 0)))
            if current_price <= 0:
                return

            # 【关键修复】每次tick都检查异常的未成交订单
            # 如果本地无持仓但有买入订单（平仓单），说明状态异常，立即取消
            if not self.position:
                try:
                    pending_orders = await self.exchange.get_orders_pending(
                        inst_type="SWAP", inst_id=self.symbol
                    )
                    if pending_orders:
                        buy_orders = [o for o in pending_orders if o.get("side") == "buy"]
                        if buy_orders:
                            logger.warning(f"⚠️  异常状态: 本地无持仓但有{len(buy_orders)}笔买入订单，立即取消")
                            await self._cancel_pending_orders()
                            # 取消后重置状态
                            self.open_position_attempted = False
                            self.waiting_reentry = False
                except Exception as check_error:
                    logger.debug(f"检查未成交订单失败: {check_error}")

            if not hasattr(self, '_health_check_count'):
                self._health_check_count = 0
            self._health_check_count += 1
            if self._health_check_count >= 60:
                self._health_check_count = 0
                logger.info(
                    f"💊 策略健康检查 [{self.symbol}] "
                    f"价格={current_price:.6f} | "
                    f"持仓={'有' if self.position else '无'} | "
                    f"等待反弹={'是' if self.waiting_reentry else '否'} | "
                    f"已尝试开仓={'是' if self.open_position_attempted else '否'} | "
                    f"冷静期={'有' if self.cooldown_until else '无'} | "
                    f"止损次数={self.stop_loss_count}/{self.max_stop_loss_count}"
                )

            if self.cooldown_until and datetime.now() < self.cooldown_until:
                return
            elif self.cooldown_until:
                logger.info(f"✅ 冷静期结束,恢复交易监控")
                self.cooldown_until = None

            # 【关键修复】每10个tick检查一次持仓和订单状态
            if not hasattr(self, '_tick_count'):
                self._tick_count = 0
            self._tick_count += 1
            if self._tick_count >= 10:
                self._tick_count = 0
                had_position_before = self.position is not None
                await self._check_existing_position()

                # 【修复1】如果开仓标志已设置但无持仓，检查未成交订单
                if self.open_position_attempted and not self.position:
                    pending_orders = await self.exchange.get_orders_pending(
                        inst_type="SWAP", inst_id=self.symbol
                    )
                    pending_count = len(pending_orders) if pending_orders else 0

                    if pending_count > 0:
                        # 有未成交订单，等待成交
                        logger.info(f"⏳ 已有{pending_count}笔未成交订单，等待成交...")
                    else:
                        # 无持仓且无未成交订单，说明开仓失败或订单被拒，重置标志
                        logger.warning("⚠️  状态异常: 开仓标志已设置但无持仓且无挂单，重置标志")
                        self.open_position_attempted = False
                        self.waiting_reentry = False

                # 【修复2】如果平仓标志设置但发现持仓仍在，清理状态
                if not self.open_position_attempted and self.position and had_position_before:
                    logger.info(f"🔄 检测到持仓存在，同步状态")
                    self.open_position_attempted = True

            if self.position:
                await self._monitor_position(current_price)
            elif self.waiting_reentry:
                await self._monitor_reentry(current_price)
            elif not self.position and not self.waiting_reentry and not self.open_position_attempted:
                logger.info("检测到无持仓且未等待反弹,尝试开仓")
                self.open_position_attempted = True
                await self._open_short_position()

        except Exception as e:
            logger.error(f"处理tick数据失败: {e}")

    async def on_order_update(self, order: Dict):
        order_id, state, side = order.get('ordId'), order.get('state'), order.get('side')
        logger.info(f"📮 订单更新: {order_id} - {state} ({side})")

        if state == "filled":
            logger.success(f"✅ 订单已成交: {order_id} - {side}")
            await self._check_existing_position()
        elif state == "canceled":
            logger.warning(f"⚠️  订单已撤销: {order_id} - {side}")
            # 先清理所有未成交订单，防止累积
            await self._cancel_pending_orders()
            if side == "sell":
                logger.info("卖出订单被撤销,重置开仓标志,允许重新尝试")
                self.open_position_attempted = False
                self.cooldown_until = datetime.now() + timedelta(minutes=1)
                logger.info(f"⏸️  设置1分钟冷静期,到 {self.cooldown_until.strftime('%H:%M:%S')}")
            elif side == "buy":
                logger.warning("买入订单被撤销,可能仍有持仓,重新检查")
                await self._check_existing_position()
        elif state == "partially_filled":
            logger.info(f"订单部分成交: {order_id} - {order.get('accFillSz')}/{order.get('sz')}")
            await self._check_existing_position()

    async def on_kline(self, kline: Dict):
        """处理K线数据(可选,本策略主要使用tick)"""
        pass

    async def _check_existing_position(self):
        try:
            positions = await self.exchange.get_positions(inst_type="SWAP", inst_id=self.symbol)
            if positions and len(positions) > 0:
                pos = positions[0]
                pos_amount = Decimal(str(pos.get("pos", 0)))

                if pos_amount < 0:  # 检测空头持仓
                    avg_price = Decimal(str(pos.get("avgPx", 0)))
                    abs_pos_amount = abs(pos_amount)

                    if self.position:
                        self.position["entry_price"] = avg_price
                        self.position["amount"] = abs_pos_amount
                        if avg_price < self.lowest_price:
                            self.lowest_price = avg_price
                            self.position["lowest_price"] = avg_price
                        logger.debug(f"更新持仓: {abs_pos_amount} @ {avg_price}")
                    else:
                        self.position = {
                            "entry_price": avg_price,
                            "amount": abs_pos_amount,
                            "contract_amount": abs_pos_amount,
                            "lowest_price": avg_price
                        }
                        self.lowest_price = avg_price
                        self.waiting_reentry = False
                        self.open_position_attempted = True
                        logger.info(f"🔍 检测到已有空头持仓: {abs_pos_amount}张 @ {avg_price}")
                else:
                    if self.position:
                        logger.info("持仓已平仓,清除持仓记录")
                    self.position = None
            else:
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
            buy_count = 0
            sell_count = 0

            for order in pending_orders:
                order_id = order.get("ordId")
                side = order.get("side")
                size = order.get("sz")
                order_type = order.get("ordType")
                state = order.get("state")
                price = order.get("px", "N/A")

                if side == "buy":
                    buy_count += 1
                elif side == "sell":
                    sell_count += 1

                logger.info(f"📋 订单: {side} {size}张 @{price} {order_type} - 状态: {state} - ID: {order_id}")

                try:
                    # 取消订单
                    result = await self.exchange.cancel_order(
                        symbol=self.symbol,
                        order_id=order_id
                    )

                    # 检查取消结果
                    if result and isinstance(result, dict):
                        code = result.get("code", "")
                        if code == "0" or result.get("result") is True:
                            logger.success(f"✅ 已取消订单: {order_id}")
                            canceled_count += 1
                        else:
                            msg = result.get("msg", result.get("msg", "未知错误"))
                            logger.error(f"❌ 取消订单 {order_id} 失败: code={code}, msg={msg}")
                            failed_count += 1
                    else:
                        logger.warning(f"⚠️  取消订单 {order_id} 返回异常: {result}")
                        failed_count += 1

                except Exception as cancel_error:
                    logger.error(f"❌ 取消订单 {order_id} 异常: {cancel_error}")
                    failed_count += 1

            # 总结
            if canceled_count > 0:
                logger.success(f"✅ 成功撤销 {canceled_count} 笔订单 (买入:{buy_count}, 卖出:{sell_count})")

                # 【修复5】取消订单后，如果全是买入订单（平仓），说明可能是错误状态，重置标志
                if buy_count > 0 and sell_count == 0:
                    logger.warning("⚠️  取消的订单全是买入订单，可能是错误平仓，重置开仓标志")
                    self.open_position_attempted = False
                    self.waiting_reentry = False

            if failed_count > 0:
                logger.warning(f"⚠️  {failed_count} 笔订单撤销失败")

            # 【新增】取消后等待一小段时间，再次检查
            if canceled_count > 0:
                await asyncio.sleep(0.3)
                remaining_orders = await self.exchange.get_orders_pending(
                    inst_type="SWAP", inst_id=self.symbol
                )
                if remaining_orders:
                    logger.warning(f"⚠️  取消后仍有{len(remaining_orders)}笔未成交订单")
                else:
                    logger.success("✅ 所有未成交订单已清理完毕")

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

    async def _open_short_position(self):
        """开空头仓位（优化版）"""
        try:
            # 【修复3】先检查未成交订单数量
            pending_orders = await self.exchange.get_orders_pending(
                inst_type="SWAP", inst_id=self.symbol
            )
            pending_count = len(pending_orders) if pending_orders else 0

            if pending_count > 3:
                logger.warning(f"⚠️  未成交订单过多({pending_count}笔)，取消旧订单后重试")
                await self._cancel_pending_orders()
                await asyncio.sleep(1)  # 等待取消完成
                # 重新检查
                pending_orders = await self.exchange.get_orders_pending(
                    inst_type="SWAP", inst_id=self.symbol
                )
                pending_count = len(pending_orders) if pending_orders else 0

            if pending_count > 0:
                logger.warning(f"⏳ 仍有{pending_count}笔未成交订单，本次跳过开仓")
                return

            await self._cancel_pending_orders()
            if not await self._check_volatility():
                return

            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = Decimal(str(ticker.get("last", 0)))
            if current_price <= 0:
                logger.error("无法获取当前价格,开仓失败")
                return

            position_ratio = Decimal("1.0")
            if self.stop_loss_count > 0 and self.stop_loss_count <= len(self.position_scale_ratios):
                position_ratio = Decimal(str(self.position_scale_ratios[self.stop_loss_count - 1]))
                logger.info(f"📊 根据第{self.stop_loss_count}次止损,调整仓位为 {position_ratio*100:.0f}%")

            if position_ratio <= 0:
                logger.warning("仓位比例为0,跳过开仓")
                return

            coin_amount = (self.initial_amount * position_ratio * self.leverage) / current_price
            contract_amount = (coin_amount / self.ct_val // self.lot_sz) * self.lot_sz

            if contract_amount < self.min_sz:
                logger.error(f"开仓数量 {contract_amount} 张小于最小下单量 {self.min_sz} 张")
                return
            if contract_amount > self.max_mkt_sz:
                contract_amount = self.max_mkt_sz

            # 【限价挂单策略】卖出时挂高价，等待价格上涨后成交
            # use_limit_orders=False -> 市价单（100%成交）
            # use_limit_orders=True -> 限价单（挂单等待，可能省手续费）
            is_simulated = getattr(self, 'is_simulated', False)
            force_market = not self.use_limit_orders
            order_type_str, order_price = "market", None
            should_use_limit = False

            if not force_market and current_price >= Decimal("0.0001"):
                # 【限价策略】卖出开空时，挂比当前价略高的价格
                # 等待价格上涨后有人来买
                limit_price = current_price * (Decimal("1") + self.limit_order_offset_pct / Decimal("100"))
                limit_price = ((limit_price // self.tick_sz) + Decimal("1")) * self.tick_sz  # 向上取整

                # 检查限价是否有效(必须至少偏离一个tickSz)
                if limit_price <= current_price:
                    logger.warning(f"⚠️  限价 {limit_price} 未高于市价 {current_price}, 改用市价单")
                elif (limit_price - current_price) < self.tick_sz:
                    logger.warning(f"⚠️  限价偏移 {limit_price - current_price} 小于tickSz {self.tick_sz}, 改用市价单")
                else:
                    should_use_limit = True
                    # 使用普通limit单（不是post_only），避免被拒绝
                    order_type_str = "limit"
                    order_price = limit_price
                    logger.info(f"📊 使用限价单开空: {contract_amount} 张 @ {limit_price} (向上偏移{self.limit_order_offset_pct}%, 挂单等待)")

            if not should_use_limit:
                # 使用市价单，确保100%成交
                order_type_str = "market"
                order_price = None
                logger.info(f"⚡ 使用市价单开空: {contract_amount} 张 (当前价: {current_price})")

            # 【调试】详细记录下单参数
            logger.info(
                f"🚀 准备下单: symbol={self.symbol}, side=sell(开空), type={order_type_str}, "
                f"amount={contract_amount}, price={order_price}, td_mode={self.margin_mode}, pos_side=net"
            )

            # 下单
            order = await self.exchange.create_order(
                symbol=self.symbol, side="sell", order_type=order_type_str,
                amount=float(contract_amount), price=float(order_price) if order_price else None,
                td_mode=self.margin_mode, pos_side="net"
            )

            # 【调试】记录交易所返回结果
            logger.info(f"📥 交易所返回: {order}")

            if order and order.get("ordId"):
                order_id = order.get("ordId")
                logger.info(f"✅ 开仓订单提交成功: {order_id}")

                # 【新增】立即查询订单状态确认
                max_retries = 2  # 最多重试2次
                for retry in range(max_retries):
                    try:
                        await asyncio.sleep(0.5)  # 等待一小段时间让订单处理
                        order_detail = await self.exchange.get_order(
                            symbol=self.symbol,
                            order_id=order_id
                        )
                        order_state = order_detail.get("state", "unknown")
                        cancel_reason = order_detail.get("cancelSourceReason", "")

                        logger.info(f"🔍 订单状态查询: {order_id} -> 状态={order_state}")

                        # 如果订单状态不是live，说明被撤销了
                        if order_state == "canceled":
                            # 先清理所有未成交订单，防止累积
                            await self._cancel_pending_orders()

                            if retry < max_retries - 1 and order_type_str == "limit":
                                # 用更大的偏移量重试
                                new_offset = self.limit_order_offset_pct * (retry + 2)  # 2倍或3倍偏移
                                new_price = current_price * (Decimal("1") + new_offset / Decimal("100"))
                                new_price = ((new_price // self.tick_sz) + Decimal("1")) * self.tick_sz

                                logger.warning(
                                    f"⚠️ 限价单被拒绝({cancel_reason})，"
                                    f"用更大偏移量重试: {new_offset}% @ {new_price}"
                                )

                                order = await self.exchange.create_order(
                                    symbol=self.symbol, side="sell", order_type="limit",
                                    amount=float(contract_amount), price=float(new_price),
                                    td_mode=self.margin_mode, pos_side="net"
                                )
                                order_id = order.get("ordId")
                                logger.info(f"🔄 重新下单: {order_id}")
                                continue  # 继续检查新订单状态
                            else:
                                logger.warning(f"⚠️ 订单被撤销，不再重试，使用市价单")
                                # 最后一次重试用市价单
                                order = await self.exchange.create_order(
                                    symbol=self.symbol, side="sell", order_type="market",
                                    amount=float(contract_amount), price=None,
                                    td_mode=self.margin_mode, pos_side="net"
                                )
                                logger.info(f"⚡ 使用市价单重新下单: {order.get('ordId')}")
                                break
                        elif order_state == "live":
                            logger.success(f"✅ 订单 {order_id} 正常挂单中")
                            break
                        else:
                            logger.info(f"📝 订单状态: {order_state}")
                            break
                    except Exception as query_error:
                        logger.warning(f"⚠️ 查询订单状态失败: {query_error}")
                        break

                # 【优化3】保存订单信息到数据库
                await self._save_order_to_db(
                    order, "sell", order_type_str, float(order_price) if order_price else None, contract_amount
                )

                # 发送开仓通知
                try:
                    margin = float(self.initial_amount) / self.leverage
                    # 使用下单时的价格作为通知的入场价格 (限价单为限价,市价单为当时市价)
                    notif_entry_price = order_price if order_price else current_price
                    await notification_service.notify_position_opened(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        strategy_name=self.strategy_name,
                        symbol=self.symbol,
                        side="sell",
                        entry_price=float(notif_entry_price),
                        amount=float(contract_amount),
                        leverage=self.leverage,
                        margin=margin
                    )
                except Exception as e:
                    logger.error(f"发送开仓通知失败: {e}")

                # 标记已尝试开仓，但不要立即设置position
                # 等待订单实际成交后，通过_check_existing_position()检测到真实持仓再设置
                self.open_position_attempted = True
                logger.info(f"⏳ 等待订单成交，将在下次检查持仓时更新策略状态")
            else:
                logger.error(f"❌ 开仓失败: {order}")
                self.cooldown_until = datetime.now() + timedelta(minutes=1)
                self.open_position_attempted = False

        except Exception as e:
            logger.error(f"开仓异常: {e}")
            # 异常时重置开仓标志，允许下次重试
            self.open_position_attempted = False
            self.cooldown_until = datetime.now() + timedelta(minutes=1)

    async def _close_position(self, reason: str):
        """平仓买入（优化版）"""
        if not self.position:
            logger.warning("⚠️ 尝试平仓但无本地持仓记录，跳过")
            return

        try:
            # 【修复4】平仓前先向交易所确认持仓状态
            positions = await self.exchange.get_positions(inst_type="SWAP", inst_id=self.symbol)
            has_real_position = False
            real_pos_amount = Decimal("0")

            if positions and len(positions) > 0:
                pos = positions[0]
                real_pos_amount = Decimal(str(pos.get("pos", 0)))
                if real_pos_amount < 0:  # 空头持仓
                    has_real_position = True

            # 如果本地显示有持仓但交易所没有，清除本地状态
            if not has_real_position:
                logger.warning(f"⚠️ 状态不一致: 本地有持仓记录但交易所无持仓(pos={real_pos_amount})，清除本地状态")
                self.position = None
                self.lowest_price = Decimal("9999999")
                self.open_position_attempted = False
                return

            contract_amount = self.position.get("contract_amount")
            if not contract_amount:
                coin_amount = self.position["amount"]
                contract_amount = coin_amount / self.ct_val

            # 获取当前价格
            ticker = await self.exchange.get_ticker(self.symbol)
            current_price = Decimal(str(ticker.get("last", 0)))

            # 判断是否是止损
            is_stop_loss = "止损" in reason

            # 【限价挂单策略】买入时挂低价，等待价格下跌后成交
            # 止损时强制使用市价单，确保立即成交
            # use_limit_orders=False -> 市价单（100%成交）
            # use_limit_orders=True -> 限价单（挂单等待，可能省手续费）
            is_simulated = getattr(self, 'is_simulated', False)
            force_market = is_stop_loss or not self.use_limit_orders
            order_type_str, order_price = "market", None
            should_use_limit = False

            if not force_market and current_price >= Decimal("0.0001"):
                # 【限价策略】平仓买入时，挂比当前价略低的价格
                # 等待价格下跌后有人来卖
                limit_price = current_price * (Decimal("1") - self.limit_order_offset_pct / Decimal("100"))
                limit_price = (limit_price // self.tick_sz) * self.tick_sz  # 向下取整

                # 检查限价是否有效(必须至少偏离一个tickSz)
                if limit_price >= current_price:
                    logger.warning(f"⚠️  限价 {limit_price} 未低于市价 {current_price}, 改用市价单")
                elif (current_price - limit_price) < self.tick_sz:
                    logger.warning(f"⚠️  限价偏移 {current_price - limit_price} 小于tickSz {self.tick_sz}, 改用市价单")
                else:
                    should_use_limit = True
                    # 使用普通limit单（不是post_only），避免被拒绝
                    order_type_str = "limit"
                    order_price = limit_price
                    logger.info(f"📊 使用限价单平仓: {contract_amount} 张 @ {limit_price} (向下偏移{self.limit_order_offset_pct}%, 挂单等待) - 原因: {reason}")

            if not should_use_limit:
                # 使用市价单，确保100%成交
                order_type_str = "market"
                order_price = None
                logger.info(f"⚡ 使用市价单平仓: {contract_amount} 张 - 原因: {reason}")

            order = await self.exchange.create_order(
                symbol=self.symbol,
                side="buy",  # 平空仓需要买入
                order_type=order_type_str,
                amount=float(contract_amount),
                price=float(order_price) if order_price else None,
                td_mode=self.margin_mode,
                pos_side="net",
                reduce_only=True  # 只减仓标志
            )

            if order and order.get("ordId"):
                logger.info(f"✅ 平仓订单提交成功: {order.get('ordId')}")

                # 保存订单到数据库
                await self._save_order_to_db(
                    order, "buy", order_type_str,
                    float(order_price) if order_price else None,
                    contract_amount
                )

                # 【优化3】计算盈亏并发送通知
                try:
                    entry_price = self.position["entry_price"]
                    coin_amount = contract_amount * self.ct_val

                    # 空头盈亏 = (开仓价 - 平仓价) × 合约张数 × 合约面值
                    pnl = (entry_price - current_price) * coin_amount
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100 * self.leverage

                    await notification_service.notify_position_closed(
                        user_id=self.user_id,
                        strategy_id=self.strategy_id,
                        strategy_name=self.strategy_name,
                        symbol=self.symbol,
                        side="sell",  # 空头
                        entry_price=float(entry_price),
                        exit_price=float(current_price),
                        amount=float(coin_amount),
                        pnl=float(pnl),
                        pnl_pct=float(pnl_pct),
                        reason=reason
                    )

                    logger.success(
                        f"💰 平仓完成: {entry_price} → {current_price} | "
                        f"盈亏={pnl:.2f} USDT ({pnl_pct:+.2f}%)"
                    )
                except Exception as e:
                    logger.error(f"发送平仓通知失败: {e}")

                # 清空持仓
                self.position = None
                self.lowest_price = Decimal("9999999")
            else:
                logger.error(f"❌ 平仓失败: {order}")

        except Exception as e:
            logger.error(f"❌ 平仓异常: {e}")

    async def _monitor_position(self, current_price: Decimal):
        """监控持仓，检查止盈止损和追踪止损"""
        if not self.position:
            return

        entry_price = self.position["entry_price"]

        # 更新最低价（用于做空，价格越低盈利越多）
        if current_price < self.lowest_price:
            self.lowest_price = current_price
            self.position["lowest_price"] = current_price

        # 新逻辑: 直接使用币价变化率进行判断
        # self.take_profit_pct 现在代表币价变化的百分比
        price_change_pct = (entry_price - current_price) / entry_price * 100

        # 【新增】追踪止损逻辑
        if self.enable_trailing_stop:
            # 使用基于币价变化的盈利百分比来激活
            if not self.trailing_stop_triggered and price_change_pct >= self.trailing_stop_activation_pct:
                self.trailing_stop_triggered = True
                self.highest_trailing_price = current_price
                logger.info(
                    f"🎯 追踪止损已激活! 当前币价盈利 {price_change_pct:.2f}%, "
                    f"激活价 {self.highest_trailing_price}, "
                    f"追踪止损线将从最低价回调 {self.trailing_stop_pct}%"
                )

            # 如果追踪止损已激活，更新最高触发价
            if self.trailing_stop_triggered:
                if current_price < self.highest_trailing_price:
                    self.highest_trailing_price = current_price
                    logger.debug(f"📍 更新追踪基准价: {self.highest_trailing_price}")

                # 计算从最低点（最有利点）的反弹幅度
                if current_price > self.highest_trailing_price:
                    drawback_from_low_pct = (current_price - self.highest_trailing_price) / self.highest_trailing_price * 100

                    if drawback_from_low_pct >= self.trailing_stop_pct:
                        logger.info(
                            f"🔔 触发追踪止损: 当前价 {current_price}, "
                            f"追踪基准价 {self.highest_trailing_price}, "
                            f"反弹 {drawback_from_low_pct:.2f}% (阈值 {self.trailing_stop_pct}%)"
                        )
                        await self._close_position(f"追踪止盈 {price_change_pct:.2f}%")
                        self._reset_position_tracking()
                        return

        # 止盈检查
        if price_change_pct >= self.take_profit_pct:
            logger.info(
                f"💰 触发止盈: 当前价 {current_price}, 开仓价 {entry_price}, "
                f"币价盈利 {price_change_pct:.2f}%"
            )
            await self._close_position(f"止盈 {price_change_pct:.2f}%")
            if self.stop_loss_count > 0:
                logger.info(f"✅ 止盈成功,重置止损次数 ({self.stop_loss_count} → 0)")
                self.stop_loss_count = 0
            self._reset_position_tracking()
            self.waiting_reentry = True
            self.reentry_trigger_price = self.lowest_price * (1 + self.reentry_pct / 100)
            logger.info(f"等待反弹卖出,触发价格: {self.reentry_trigger_price}")
            return

        # 止损检查
        if price_change_pct <= -self.stop_loss_pct:
            logger.warning(
                f"🛑 触发止损: 当前价 {current_price}, 开仓价 {entry_price}, "
                f"币价亏损 {price_change_pct:.2f}%"
            )
            await self._close_position(f"止损 {price_change_pct:.2f}%")
            self.stop_loss_count += 1
            logger.warning(f"⚠️  第 {self.stop_loss_count} 次止损 (最大允许 {self.max_stop_loss_count} 次)")

            # 设置冷静期
            self.cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
            logger.info(f"🕐 进入冷静期,持续 {self.cooldown_minutes} 分钟,到 {self.cooldown_until.strftime('%H:%M:%S')}")

            if self.stop_loss_count >= self.max_stop_loss_count:
                logger.error(f"❌ 达到最大止损次数 {self.max_stop_loss_count},策略停止交易,等待人工介入")
                self.waiting_reentry = False
                self.open_position_attempted = True
            else:
                # 还可以继续交易，冷静期后以降低的仓位重新开仓
                position_ratio = self.position_scale_ratios[self.stop_loss_count - 1]
                logger.info(f"📊 冷静期后将以 {position_ratio*100:.0f}% 仓位重新开仓")
                self.waiting_reentry = True
                self.open_position_attempted = False

            self._reset_position_tracking()
            return

    def _reset_position_tracking(self):
        """重置持仓追踪状态"""
        self.position = None
        self.lowest_price = Decimal("9999999")
        self.trailing_stop_triggered = False
        self.highest_trailing_price = Decimal("0")

    async def _monitor_reentry(self, current_price: Decimal):
        if not self.waiting_reentry: return
        if current_price >= self.reentry_trigger_price:
            logger.info(f"触发反弹卖出: 当前价格 {current_price}, 触发价 {self.reentry_trigger_price}")
            self.waiting_reentry = False
            await self._open_short_position()

    async def calculate_pnl(self) -> Dict:
        """
        计算波段做空策略的实时盈亏

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

            db = SessionLocal()
            try:
                orders = db.query(OrderModel).filter(
                    OrderModel.strategy_id == self.strategy_id,
                    OrderModel.status.in_([OrderStatus.FILLED, OrderStatus.PARTIAL_FILLED])
                ).all()

                buy_total = Decimal("0")
                sell_total = Decimal("0")
                buy_amount_sum = Decimal("0")
                sell_amount_sum = Decimal("0")
                total_fee = Decimal("0")

                for order in orders:
                    fee = Decimal(str(order.fee or 0))
                    total_fee += fee
                    price = Decimal(str(order.avg_price or order.price or 0))
                    # amount is in contracts, need to convert to coin amount for pnl
                    coin_amount = Decimal(str(order.filled_amount or 0)) * self.ct_val
                    side = order.side.value if hasattr(order.side, 'value') else str(order.side)

                    if side.lower() == 'buy':
                        result["buy_count"] += 1
                        buy_total += price * coin_amount
                        buy_amount_sum += coin_amount
                    elif side.lower() == 'sell':
                        result["sell_count"] += 1
                        sell_total += price * coin_amount
                        sell_amount_sum += coin_amount
                
                if buy_amount_sum > 0:
                    result["avg_buy_price"] = float(buy_total / buy_amount_sum)
                if sell_amount_sum > 0:
                    result["avg_sell_price"] = float(sell_total / sell_amount_sum)

                result["total_buy_amount"] = float(buy_total)
                result["total_sell_amount"] = float(sell_total)
                result["realized_pnl"] = float(sell_total - buy_total - total_fee)
                result["total_fee"] = float(total_fee)

                try:
                    positions = await self.exchange.get_positions(inst_type="SWAP", inst_id=self.symbol)
                    if positions and len(positions) > 0:
                        pos = positions[0]
                        pos_size = Decimal(str(pos.get("pos", "0")))

                        if pos_size < 0: # Short position
                            unrealized_pnl = Decimal(str(pos.get("upl", "0")))
                            mark_px = Decimal(str(pos.get("markPx", "0")))
                            result["current_position"] = abs(float(pos_size))
                            result["position_value"] = float(mark_px * abs(pos_size) * self.ct_val)
                            result["unrealized_pnl"] = float(unrealized_pnl)
                        else:
                             result["unrealized_pnl"] = 0.0
                    elif self.position: # Fallback to manual calculation if API fails
                        ticker = await self.exchange.get_ticker(self.symbol)
                        current_price = Decimal(str(ticker.get("last", 0)))
                        contract_amount = self.position.get("contract_amount", 0)
                        entry_price = self.position.get("entry_price", 0)
                        
                        result["current_position"] = float(contract_amount)
                        result["position_value"] = float(current_price * Decimal(str(contract_amount)) * self.ct_val)
                        # Unrealized PNL for short = (entry_price - current_price) * amount_in_coin
                        result["unrealized_pnl"] = float(
                            (Decimal(str(entry_price)) - current_price) * (Decimal(str(contract_amount)) * self.ct_val)
                        )

                except Exception as pos_error:
                    logger.warning(f"获取持仓失败，无法计算未实现盈亏: {pos_error}")
                    result["unrealized_pnl"] = 0.0

                result["total_pnl"] = result["realized_pnl"] + result["unrealized_pnl"]
                if self.initial_amount > 0:
                    result["pnl_rate"] = (result["total_pnl"] / float(self.initial_amount)) * 100

            finally:
                db.close()

            return result

        except Exception as e:
            logger.error(f"计算盈亏失败: {e}")
            # Return a default structure on failure
            return {
                "total_pnl": 0.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0, "total_fee": 0.0,
                "pnl_rate": 0.0, "buy_count": 0, "sell_count": 0, "total_buy_amount": 0.0,
                "total_sell_amount": 0.0, "avg_buy_price": 0.0, "avg_sell_price": 0.0,
                "current_position": 0.0, "position_value": 0.0
            }
