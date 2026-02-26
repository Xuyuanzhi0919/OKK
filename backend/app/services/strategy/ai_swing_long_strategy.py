"""
AI增强波段做多策略

在原有波段策略基础上,增加AI智能分析和决策:
1. AI分析市场情绪
2. 智能加仓/减仓建议
3. 动态调整止盈止损
4. 风险预警
"""

from decimal import Decimal
from typing import Dict, Optional
from loguru import logger
from .swing_long_strategy import SwingLongStrategy
from app.services.ai.ai_analyzer import ai_analyzer
from app.services.ai.llm_enhanced_analyzer import llm_enhanced_analyzer


class AISwingLongStrategy(SwingLongStrategy):
    """AI增强波段做多策略"""

    def __init__(
        self,
        strategy_id: int,
        exchange,
        symbol: str,
        parameters: Dict,
        user_id: int = 1
    ):
        super().__init__(strategy_id, exchange, symbol, parameters, user_id)

        # AI相关配置
        self.enable_ai = parameters.get("enable_ai", True)  # 是否启用AI
        self.ai_confidence_threshold = Decimal(str(parameters.get("ai_confidence_threshold", "0.7")))  # AI信心度阈值
        self.ai_analysis_interval = parameters.get("ai_analysis_interval", 300)  # AI分析间隔(秒)
        self.last_ai_analysis_time = None
        self.last_ai_result = None

        # LLM增强配置
        self.enable_llm = parameters.get("enable_llm", True)  # 是否启用LLM分析
        self.enable_news_analysis = parameters.get("enable_news_analysis", True)  # 是否启用新闻分析

        # 智能仓位管理
        self.enable_smart_position = parameters.get("enable_smart_position", True)  # 智能加减仓
        self.max_position_ratio = Decimal(str(parameters.get("max_position_ratio", "2.0")))  # 最大仓位倍数

        logger.info(
            f"AI增强策略初始化: AI={'启用' if self.enable_ai else '禁用'}, "
            f"LLM={'启用' if self.enable_llm else '禁用'}, "
            f"新闻分析={'启用' if self.enable_news_analysis else '禁用'}, "
            f"信心度阈值={self.ai_confidence_threshold}, "
            f"智能仓位={'启用' if self.enable_smart_position else '禁用'}"
        )

    async def on_tick(self, ticker: Dict):
        """
        处理实时行情 - 增加AI分析

        流程:
        1. 调用父类的基础监控
        2. 定期进行AI分析
        3. 根据AI建议执行加仓/减仓
        """
        # 先执行基础策略逻辑
        await super().on_tick(ticker)

        # AI增强逻辑
        if self.enable_ai and self.is_running:
            await self._ai_enhanced_decision(ticker)

    async def _ai_enhanced_decision(self, ticker: Dict):
        """
        AI增强决策逻辑
        """
        try:
            # 检查是否需要进行AI分析(避免频繁分析)
            from datetime import datetime, timedelta
            now = datetime.now()

            if self.last_ai_analysis_time:
                elapsed = (now - self.last_ai_analysis_time).total_seconds()
                if elapsed < self.ai_analysis_interval:
                    return  # 未到分析时间

            # 执行AI分析
            current_price = Decimal(str(ticker.get("last", 0)))
            if current_price <= 0:
                return

            # 根据配置选择分析器
            if self.enable_llm:
                # 使用LLM增强分析器
                ai_result = await llm_enhanced_analyzer.analyze_market_with_llm(
                    symbol=self.symbol,
                    current_price=current_price,
                    ticker_data=ticker,
                    use_llm=True,
                    use_news=self.enable_news_analysis
                )
            else:
                # 使用基础规则分析器
                ai_result = await ai_analyzer.analyze_market(
                    symbol=self.symbol,
                    current_price=current_price,
                    entry_price=self.position.get("entry_price") if self.position else None,
                    position_size=self.position.get("amount") if self.position else None,
                    ticker_data=ticker
                )

            self.last_ai_result = ai_result
            self.last_ai_analysis_time = now

            # 记录AI分析结果
            logger.info(
                f"🤖 AI分析: {ai_result['action']} "
                f"(信心度: {ai_result['confidence']:.0%}, "
                f"风险: {ai_result['risk_level']}) - {ai_result['reason']}"
            )

            # 根据AI建议执行操作
            await self._execute_ai_advice(ai_result, current_price)

        except Exception as e:
            logger.error(f"AI决策失败: {e}")

    async def _execute_ai_advice(self, ai_result: Dict, current_price: Decimal):
        """
        执行AI建议

        Args:
            ai_result: AI分析结果
            current_price: 当前价格
        """
        action = ai_result.get("action")
        confidence = ai_result.get("confidence", 0)
        position_advice = ai_result.get("position_advice", {})

        # 检查信心度是否达到阈值
        if confidence < float(self.ai_confidence_threshold):
            logger.info(f"⏸️  AI信心度 {confidence:.0%} 低于阈值 {self.ai_confidence_threshold:.0%}, 不执行建议")
            return

        # 执行建议
        if not self.enable_smart_position:
            logger.info("智能仓位管理已禁用,仅记录AI建议")
            return

        # 加仓建议
        if position_advice.get("action") == "add" and self.position:
            add_ratio = position_advice.get("ratio", 0)
            if add_ratio > 0:
                await self._smart_add_position(current_price, add_ratio, ai_result["reason"])

        # 减仓建议
        elif position_advice.get("action") == "reduce" and self.position:
            reduce_ratio = position_advice.get("ratio", 0)
            if reduce_ratio > 0:
                await self._smart_reduce_position(current_price, reduce_ratio, ai_result["reason"])

        # 强烈卖出信号
        elif action == "sell" and confidence > 0.85 and self.position:
            logger.warning(f"⚠️  AI强烈建议卖出 (信心度 {confidence:.0%}), 执行平仓")
            await self._close_position(f"AI建议: {ai_result['reason']}")

    async def _smart_add_position(self, current_price: Decimal, add_ratio: float, reason: str):
        """
        智能加仓

        Args:
            current_price: 当前价格
            add_ratio: 加仓比例 (0-1)
            reason: 加仓原因
        """
        try:
            if not self.position:
                logger.warning("无持仓,无法加仓")
                return

            # 检查是否超过最大仓位
            current_amount = self.position.get("amount", 0)
            base_amount = (self.initial_amount * self.leverage) / self.position["entry_price"]

            if current_amount >= base_amount * float(self.max_position_ratio):
                logger.warning(f"已达最大仓位 ({self.max_position_ratio}倍), 不再加仓")
                return

            # 计算加仓数量
            add_amount = base_amount * Decimal(str(add_ratio))
            add_contract_amount = add_amount / self.ct_val
            add_contract_amount = (add_contract_amount // self.lot_sz) * self.lot_sz

            if add_contract_amount < self.min_sz:
                logger.warning(f"加仓数量 {add_contract_amount} 小于最小下单量 {self.min_sz}")
                return

            logger.info(f"🎯 AI建议加仓: {add_contract_amount} 张 ({add_ratio:.0%}) - {reason}")

            # 执行加仓 (使用市价单,确保成交)
            order = await self.exchange.create_order(
                symbol=self.symbol,
                side="buy",
                order_type="market",
                amount=float(add_contract_amount),
                td_mode=self.margin_mode,
                pos_side="net"
            )

            if order and order.get("ordId"):
                logger.success(f"✅ 加仓成功: {order.get('ordId')}")

                # 更新持仓 (需要重新查询真实持仓)
                await self._check_existing_position()

        except Exception as e:
            logger.error(f"❌ 加仓失败: {e}")

    async def _smart_reduce_position(self, current_price: Decimal, reduce_ratio: float, reason: str):
        """
        智能减仓

        Args:
            current_price: 当前价格
            reduce_ratio: 减仓比例 (0-1)
            reason: 减仓原因
        """
        try:
            if not self.position:
                logger.warning("无持仓,无法减仓")
                return

            # 计算减仓数量
            current_contract_amount = self.position.get("contract_amount", 0)
            if not current_contract_amount:
                current_amount = self.position.get("amount", 0)
                current_contract_amount = current_amount / self.ct_val

            reduce_contract_amount = current_contract_amount * Decimal(str(reduce_ratio))
            reduce_contract_amount = (reduce_contract_amount // self.lot_sz) * self.lot_sz

            if reduce_contract_amount < self.min_sz:
                logger.warning(f"减仓数量 {reduce_contract_amount} 小于最小下单量 {self.min_sz}")
                return

            logger.info(f"📉 AI建议减仓: {reduce_contract_amount} 张 ({reduce_ratio:.0%}) - {reason}")

            # 执行减仓
            order = await self.exchange.create_order(
                symbol=self.symbol,
                side="sell",
                order_type="market",
                amount=float(reduce_contract_amount),
                td_mode=self.margin_mode,
                pos_side="net",
                reduce_only=True
            )

            if order and order.get("ordId"):
                logger.success(f"✅ 减仓成功: {order.get('ordId')}")

                # 更新持仓
                await self._check_existing_position()

        except Exception as e:
            logger.error(f"❌ 减仓失败: {e}")

    async def get_ai_status(self) -> Dict:
        """
        获取AI状态信息

        Returns:
            AI配置和最新分析结果
        """
        return {
            "enabled": self.enable_ai,
            "confidence_threshold": float(self.ai_confidence_threshold),
            "analysis_interval": self.ai_analysis_interval,
            "last_analysis_time": self.last_ai_analysis_time.isoformat() if self.last_ai_analysis_time else None,
            "last_result": self.last_ai_result,
            "smart_position_enabled": self.enable_smart_position,
            "max_position_ratio": float(self.max_position_ratio)
        }
