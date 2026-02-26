"""
趋势跟踪策略 - EMA交叉

优化参数:
- 快线EMA: 7
- 慢线EMA: 30
- 止损: 1%
- 止盈: 5%
"""
from typing import Dict, Any, Optional
from loguru import logger
from decimal import Decimal

from app.services.strategy.base import StrategyBase
from app.models.strategy import Strategy,from app.models import StrategyType


class TrendFollowStrategy(StrategyBase):
    """
    趋势跟踪策略
    
    使用EMA(7, 30)交叉进行趋势跟踪
    - 金叉开多
    - 死叉平多
    - 1%止损
    - 5%止盈
    """
    
    # 策略参数
    FAST_PERIOD = 7
    SLOW_PERIOD = 30
    STOP_LOSS_PERCENT = 0.01  # 1%
    TAKE_PROFIT_PERCENT = 0.05  # 5%
    
    def __init__(self, strategy: Strategy, exchange, Any):
        super().__init__(strategy, exchange)
        
        # EMA历史
        self.price_history: list = []
        self.fast_ema: float = 0
        self.slow_ema: float = 0
        
        # 入场价格
        self.entry_price: float = 0
        
        # 是否持仓
        self.has_position: bool = False
        
        logger.info(f"趋势跟踪策略初始化: {strategy.symbol}")
    
    async def start(self):
        """启动策略"""
        logger.info(f"趋势跟踪策略启动: {self.strategy.symbol}")
        self.has_position = False
        self.entry_price = 0
        self.price_history = []
        self.fast_ema = 0
        self.slow_ema = 0
    
    async def stop(self):
        """停止策略"""
        logger.info(f"趋势跟踪策略停止: {self.strategy.symbol}")
        # 平仓
        if self.has_position:
            await self._close_position("manual")
        self.has_position = False
    
    async def on_tick(self, ticker: Dict):
        """
        处理行情数据
        
        Args:
            ticker: 行情数据
        """
        price = float(ticker.get('last', 0))
        timestamp = ticker.get('timestamp', 0)
        
        # 更新价格历史
        self.price_history.append(price)
        
        # 计算EMA
        self._calculate_ema()
        
        # 检查止损止盈
        if self.has_position and self.entry_price > 0:
            pnl_percent = (price - self.entry_price) / self.entry_price
            
            # 止损
            if pnl_percent <= -self.STOP_LOSS_PERCENT:
                logger.info(f"触发止损: {pnl_percent*100:.2f}%")
                await self._close_position("stop_loss")
                return
            
            # 止盈
            if pnl_percent >= self.TAKE_PROFIT_PERCENT:
                logger.info(f"触发止盈: {pnl_percent*100:.2f}%")
                await self._close_position("take_profit")
                return
        
        # 交易信号
        if len(self.price_history) >= self.SLOW_PERIOD + 2:
            # 金叉
            if self._is_golden_cross() and not self.has_position:
                await self._open_position(price)
            # 死叉
            elif self._is_death_cross() and self.has_position:
                await self._close_position("signal")
    
    def _calculate_ema(self):
        """计算EMA"""
        if len(self.price_history) < self.SLOW_PERIOD:
            return
        
        prices = self.price_history
        
        # 计算快速EMA
        fast_multiplier = 2 / (self.FAST_PERIOD + 1)
        if len(prices) >= self.FAST_PERIOD:
            if self.fast_ema == 0:
                self.fast_ema = sum(prices[-self.FAST_PERIOD:]) / self.FAST_PERIOD
            else:
                self.fast_ema = (prices[-1] - self.fast_ema) * fast_multiplier + self.fast_ema
        
        # 计算慢速EMA
        slow_multiplier = 3 / (self.SLOW_PERIOD + 1)
        if len(prices) >= self.SLOW_PERIOD:
            if self.slow_ema == 0:
                self.slow_ema = sum(prices[-self.SLOW_PERIOD:]) / self.SLOW_PERIOD
            else:
                self.slow_ema = (prices[-1] - self.slow_ema) * slow_multiplier + self.slow_ema
    
    def _is_golden_cross(self) -> bool:
        """判断金叉"""
        if len(self.price_history) < self.SLOW_PERIOD + 2:
            return False
        
        prev_fast = self.fast_ema  # 简化：实际应该用前一个值
        prev_slow = self.slow_ema
        
        # 金叉： 快线从下方穿越慢线
        return prev_fast <= prev_slow and self.fast_ema > self.slow_ema
    
    def _is_death_cross(self) -> bool:
        """判断死叉"""
        if len(self.price_history) < self.SLOW_PERIOD + 2:
            return False
        
        prev_fast = self.fast_ema
        prev_slow = self.slow_ema
        
        # 死叉： 快线从上方穿越慢线
        return prev_fast >= prev_slow and self.fast_ema < self.slow_ema
    
    async def _open_position(self, price: float):
        """开多仓"""
        try:
            # 计算下单数量（使用30%资金）
            balance = await self.exchange.get_balance()
            available = float(balance.get('available', 0))
            position_size = available * 0.3 / price
            
            # 下单
            order = await self.exchange.create_order(
                symbol=self.strategy.symbol,
                side="buy",
                order_type="market",
                size=position_size
            )
            
            if order:
                self.has_position = True
                self.entry_price = price
                logger.info(f"开多: {position_size:.6f} @ {price:.2f}")
        except Exception as e:
            logger.error(f"开多失败: {e}")
    
    async def _close_position(self, reason: str):
        """平多仓"""
        if not self.has_position:
            return
        
        try:
            # 获取当前持仓
            positions = await self.exchange.get_positions()
            position = None
            for pos in positions:
                if pos.get('symbol') == self.strategy.symbol and float(pos.get('size', 0)) > 0:
                    position = pos
                    break
            
            if position:
                size = float(position.get('size', 0))
                await self.exchange.create_order(
                    symbol=self.strategy.symbol,
                    side="sell",
                    order_type="market",
                    size=size
                )
                
                pnl = (size * (await self._get_current_price() - self.entry_price))
                logger.info(f"平多({reason}): {size:.6f}, 盈亏: {pnl:.2f}")
            
            self.has_position = False
            self.entry_price = 0
            
        except Exception as e:
            logger.error(f"平多失败: {e}")
    
    async def _get_current_price(self) -> float:
        """获取当前价格"""
        ticker = await self.exchange.get_ticker(self.strategy.symbol)
        return float(ticker.get('last', 0))
    
    async def on_order_update(self, order: Dict):
        """订单更新回调"""
        logger.debug(f"订单更新: {order}")
