"""
网格策略参数智能推荐器
"""
from typing import Dict
from decimal import Decimal
from loguru import logger


class GridRecommender:
    """网格策略参数推荐器"""

    def __init__(self, exchange):
        """
        初始化推荐器

        Args:
            exchange: 交易所实例
        """
        self.exchange = exchange

    async def recommend_params(
        self,
        symbol: str,
        total_amount: float,
        price_range_percent: float = 0.15,  # 价格区间百分比 (±15%)
        target_profit_per_grid: float = 0.015,  # 每格目标利润率 (1.5%)
    ) -> Dict:
        """
        推荐网格策略参数

        Args:
            symbol: 交易对
            total_amount: 总投资金额(USDT)
            price_range_percent: 价格区间百分比(默认±15%)
            target_profit_per_grid: 每格目标利润率(默认1.5%)

        Returns:
            推荐参数字典
        """
        try:
            # 1. 获取当前市场价格
            ticker = await self.exchange.get_ticker(symbol)
            current_price = float(ticker.get("last", 0))

            if current_price <= 0:
                raise ValueError(f"无法获取有效的市场价格: {symbol}")

            logger.info(f"当前市场价格: {current_price} USDT")

            # 2. 计算价格区间
            price_upper = current_price * (1 + price_range_percent)
            price_lower = current_price * (1 - price_range_percent)

            # 3. 计算推荐网格数量
            # 基于目标利润率和价格区间计算理想网格数
            # 网格数 = 价格区间 / (当前价格 × 目标利润率)
            ideal_grid_num = int((price_upper - price_lower) / (current_price * target_profit_per_grid))

            # 限制网格数量在合理范围内
            if total_amount < 100:
                grid_num = min(max(ideal_grid_num, 5), 10)  # 小额资金: 5-10个网格
            elif total_amount < 500:
                grid_num = min(max(ideal_grid_num, 8), 15)  # 中等资金: 8-15个网格
            else:
                grid_num = min(max(ideal_grid_num, 10), 20)  # 大额资金: 10-20个网格

            # 4. 计算每格投入金额和利润
            amount_per_grid = total_amount / grid_num
            grid_step = (price_upper - price_lower) / grid_num
            profit_per_grid_percent = (grid_step / current_price) * 100

            # 5. 风险评估
            max_drawdown_percent = price_range_percent * 100  # 最大可能回撤
            estimated_daily_trades = self._estimate_daily_trades(grid_num, current_price)
            estimated_daily_profit = estimated_daily_trades * amount_per_grid * (profit_per_grid_percent / 100)

            # 6. 获取产品信息获取最小订单量
            try:
                instruments = await self.exchange.get_instruments(
                    inst_type="SPOT",
                    inst_id=symbol
                )
                min_order_size = float(instruments[0].get("minSz", "0.001")) if instruments else 0.001
            except Exception as e:
                logger.warning(f"获取产品最小订单量失败: {e}, 使用默认值0.001")
                min_order_size = 0.001

            # 7. 验证每格数量是否满足最小要求
            size_per_grid = amount_per_grid / current_price
            if size_per_grid < min_order_size:
                # 如果不满足,减少网格数量
                recommended_grid_num = int(total_amount / (min_order_size * current_price))
                if recommended_grid_num < 3:
                    raise ValueError(
                        f"投资金额过小,至少需要 {min_order_size * current_price * 3:.2f} USDT "
                        f"才能运行网格策略(最小订单量: {min_order_size} {symbol.split('-')[0]})"
                    )
                grid_num = min(recommended_grid_num, 20)
                amount_per_grid = total_amount / grid_num
                size_per_grid = amount_per_grid / current_price

            # 8. 根据价格大小动态确定精度
            if current_price >= 1000:
                price_precision = 2
            elif current_price >= 1:
                price_precision = 4
            elif current_price >= 0.01:
                price_precision = 6
            else:
                price_precision = 8

            # 9. 构建推荐参数
            params = {
                "symbol": symbol,
                "current_price": round(current_price, price_precision),
                "price_upper": round(price_upper, price_precision),
                "price_lower": round(price_lower, price_precision),
                "grid_num": grid_num,
                "total_amount": total_amount,
                "amount_per_grid": round(amount_per_grid, 2),
                "min_order_size": min_order_size,
                "size_per_grid": round(size_per_grid, 6),
                "grid_step": round(grid_step, price_precision),
                "profit_per_grid_percent": round(profit_per_grid_percent, 2),
                "price_range_percent": round(price_range_percent * 100, 1),
                "risk_assessment": {
                    "max_drawdown_percent": round(max_drawdown_percent, 1),
                    "estimated_daily_trades": estimated_daily_trades,
                    "estimated_daily_profit": round(estimated_daily_profit, 2),
                    "risk_level": self._calculate_risk_level(max_drawdown_percent, grid_num),
                },
                "recommendations": self._generate_recommendations(
                    total_amount,
                    grid_num,
                    profit_per_grid_percent,
                    max_drawdown_percent
                )
            }

            logger.info(f"参数推荐完成: 网格数={grid_num}, 价格区间=[{price_lower:.2f}, {price_upper:.2f}]")

            return params

        except Exception as e:
            logger.error(f"推荐参数失败: {e}")
            raise

    def _estimate_daily_trades(self, grid_num: int, current_price: float) -> int:
        """
        估算每日交易次数

        基于历史数据,波动率越大,网格数越多,交易越频繁
        这里使用简化公式
        """
        # 假设BTC等主流币种日波动率约3-5%
        daily_volatility = 0.04  # 4%

        # 预计触发的网格数 = 日波动幅度 / 单格利润率
        expected_triggers = (current_price * daily_volatility) / (current_price * 0.015)

        # 每次触发意味着1次买入+1次卖出=2次交易
        estimated_trades = int(expected_triggers * 2)

        return max(1, min(estimated_trades, grid_num * 2))  # 限制在合理范围

    def _calculate_risk_level(self, max_drawdown: float, grid_num: int) -> str:
        """
        计算风险等级

        Args:
            max_drawdown: 最大回撤百分比
            grid_num: 网格数量

        Returns:
            风险等级: 低/中/高
        """
        if max_drawdown < 10 and grid_num >= 15:
            return "低"
        elif max_drawdown < 20 and grid_num >= 10:
            return "中"
        else:
            return "高"

    def _generate_recommendations(
        self,
        total_amount: float,
        grid_num: int,
        profit_per_grid: float,
        max_drawdown: float
    ) -> list:
        """
        生成使用建议

        Returns:
            建议列表
        """
        recommendations = []

        # 资金建议
        if total_amount < 100:
            recommendations.append("💡 投资金额较小,建议增加至100 USDT以上以获得更好的网格效果")
        elif total_amount > 10000:
            recommendations.append("✅ 投资金额充足,可以考虑分散到多个交易对降低风险")

        # 网格数量建议
        if grid_num < 8:
            recommendations.append("💡 网格数量较少,利润率较高但交易频率低,适合大波动行情")
        elif grid_num > 15:
            recommendations.append("✅ 网格数量较多,交易频繁,适合震荡行情")

        # 利润率建议
        if profit_per_grid < 1:
            recommendations.append("⚠️ 单格利润率较低(<1%),建议增加价格区间或减少网格数")
        elif profit_per_grid > 3:
            recommendations.append("💡 单格利润率较高(>3%),交易频率可能较低")

        # 风险建议
        if max_drawdown > 20:
            recommendations.append("⚠️ 价格区间较大(>20%),请确保有足够的风险承受能力")

        # 通用建议
        recommendations.append("📊 建议设置止损(如-10%)和止盈(如+30%)以控制风险")
        recommendations.append("🔄 震荡行情下网格策略表现最佳,单边行情需谨慎")

        return recommendations
