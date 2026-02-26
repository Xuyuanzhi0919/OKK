"""
RSI+布林带突破策略回测

策略逻辑：
1. RSI < 30 超卖区买入信号
2. RSI > 70 超买区卖出信号
3. 价格突破布林带上轨做空
4. 价格突破布林带下轨做多
5. 结合EMA趋势过滤
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from datetime import datetime, timedelta
from loguru import logger
from typing import List, Dict
from dataclasses import dataclass
from app.core.database import SessionLocal
from app.services.backtest.backtest_engine import BacktestEngine, Trade
from app.services.backtest.metrics import BacktestMetrics
from app.models import Kline
from sqlalchemy import and_


@dataclass
class Position:
    """持仓信息"""
    amount: float = 0.0
    avg_price: float = 0.0
    direction: str = "flat"  # long/short/flat


class RSIBollingerEngine(BacktestEngine):
    """RSI+布林带突破策略回测引擎"""
    
    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
        bollinger_period: int = 20,
        bollinger_std: float = 2.0,
        ema_period: int = 50,
        amount_per_trade: float = 0.01,
        fee_rate: float = 0.0005,
        leverage: int = 3,
        enable_short: bool = True,
    ):
        super().__init__(
            symbol=symbol,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            leverage=leverage,
            enable_short=enable_short
        )
        
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std
        self.ema_period = ema_period
        self.amount_per_trade = amount_per_trade
        self.enable_short = enable_short
        
        # 价格历史
        self.price_history: List[float] = []
        
        # 指标历史
        self.rsi_history: List[float] = []
        self.upper_band_history: List[float] = []
        self.lower_band_history: List[float] = []
        self.ema_history: List[float] = []
        
        logger.info(f"RSI+布林带策略初始化: RSI周期={rsi_period}, 布林带周期={bollinger_period}, EMA周期={ema_period}")
    
    def reset(self):
        super().reset()
        self.price_history = []
        self.rsi_history = []
        self.upper_band_history = []
        self.lower_band_history = []
        self.ema_history = []
    
    def calculate_rsi(self, prices: List[float], period: int) -> float:
        """计算RSI"""
        if len(prices) < period + 1:
            return 50  # 默认中性值
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_bollinger(self, prices: List[float], period: int, std_mult: float) -> tuple:
        """计算布林带"""
        if len(prices) < period:
            last_price = prices[-1] if prices else 0
            return last_price, last_price, last_price
        
        recent_prices = prices[-period:]
        sma = sum(recent_prices) / period
        
        # 计算标准差
        variance = sum((p - sma) ** 2 for p in recent_prices) / period
        std = variance ** 0.5
        
        upper = sma + std_mult * std
        lower = sma - std_mult * std
        
        return upper, sma, lower
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """计算EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def on_kline(self, kline: Dict):
        """处理K线数据"""
        timestamp = int(kline['timestamp'])
        close_price = float(kline['close'])
        high_price = float(kline['high'])
        low_price = float(kline['low'])
        
        # 更新价格历史
        self.price_history.append(close_price)
        self.current_kline = kline
        
        # 计算指标
        rsi = self.calculate_rsi(self.price_history, self.rsi_period)
        upper, middle, lower = self.calculate_bollinger(
            self.price_history, self.bollinger_period, self.bollinger_std
        )
        ema = self.calculate_ema(self.price_history, self.ema_period)
        
        # 保存指标历史
        self.rsi_history.append(rsi)
        self.upper_band_history.append(upper)
        self.lower_band_history.append(lower)
        self.ema_history.append(ema)
        
        # 需要足够的数据才能交易
        if len(self.price_history) < max(self.rsi_period, self.bollinger_period, self.ema_period) + 1:
            return
        
        prev_rsi = self.rsi_history[-2] if len(self.rsi_history) > 1 else 50
        
        # 获取当前持仓状态
        has_long = self.position.amount > 0
        has_short = self.position.amount < 0
        
        # === 做多信号 ===
        # 信号1: RSI从超卖区回升
        rsi_buy_signal = prev_rsi < self.rsi_oversold and rsi > self.rsi_oversold
        
        # 信号2: 价格触及布林带下轨后反弹
        bb_buy_signal = low_price <= self.lower_band_history[-2] and close_price > lower
        
        # 信号3: 价格在EMA上方（趋势过滤）
        trend_up = close_price > ema
        
        # === 做空信号 ===
        # 信号1: RSI从超买区回落
        rsi_sell_signal = prev_rsi > self.rsi_overbought and rsi < self.rsi_overbought
        
        # 信号2: 价格触及布林带上轨后回落
        bb_sell_signal = high_price >= self.upper_band_history[-2] and close_price < upper
        
        # 信号3: 价格在EMA下方（趋势过滤）
        trend_down = close_price < ema
        
        # 执行交易逻辑
        if not has_long and not has_short:
            # 无持仓，寻找入场机会
            if rsi_buy_signal or (bb_buy_signal and trend_up):
                # 做多信号
                trade = self.buy(close_price, self.amount_per_trade, timestamp)
                if trade:
                    logger.debug(f"做多: RSI={rsi:.1f}, 价格={close_price:.2f}, 布林下轨={lower:.2f}")
            
            elif self.enable_short and (rsi_sell_signal or (bb_sell_signal and trend_down)):
                # 做空信号
                trade = self.short(close_price, self.amount_per_trade, timestamp)
                if trade:
                    logger.debug(f"做空: RSI={rsi:.1f}, 价格={close_price:.2f}, 布林上轨={upper:.2f}")
        
        elif has_long:
            # 持有多头，检查平仓信号
            if rsi_sell_signal or bb_sell_signal:
                trade = self.sell(close_price, self.amount_per_trade, timestamp)
                if trade:
                    logger.debug(f"平多: RSI={rsi:.1f}, 盈亏={trade.pnl:.2f}")
        
        elif has_short:
            # 持有空头，检查平仓信号
            if rsi_buy_signal or bb_buy_signal:
                trade = self.cover(close_price, self.amount_per_trade, timestamp)
                if trade:
                    logger.debug(f"平空: RSI={rsi:.1f}, 盈亏={trade.pnl:.2f}")


async def fetch_klines():
    """获取K线数据"""
    from app.services.exchange.okx import OKXExchange
    from app.services.backtest.kline_service import KlineService
    
    db = SessionLocal()
    try:
        exchange = OKXExchange(api_key="", secret_key="", passphrase="", simulated=True)
        kline_service = KlineService(db, exchange)
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=3)
        
        result = await kline_service.fetch_and_save_klines(
            symbol="BTC-USDT-SWAP",
            interval="15m",
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000)
        )
        
        print(f"获取K线数据: {result}")
        await exchange.close()
        return result
    except Exception as e:
        logger.error(f"获取K线失败: {e}")
        return None
    finally:
        db.close()


def run_backtest():
    """运行回测"""
    db = SessionLocal()
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=3)
        
        klines = db.query(Kline).filter(
            and_(
                Kline.symbol == "BTC-USDT-SWAP",
                Kline.interval == "15m",
                Kline.timestamp >= int(start_time.timestamp() * 1000),
                Kline.timestamp <= int(end_time.timestamp() * 1000)
            )
        ).order_by(Kline.timestamp.asc()).all()
        
        if not klines:
            print("没有K线数据")
            return
        
        print(f"\n{'='*60}")
        print(f"RSI+布林带突破策略 - 3倍杠杆合约回测")
        print(f"{'='*60}")
        print(f"交易对: BTC-USDT-SWAP")
        print(f"K线周期: 15分钟")
        print(f"回测天数: 3天")
        print(f"初始资金: 10000 USDT")
        print(f"杠杆: 3x")
        
        first_price = float(klines[0].open)
        last_price = float(klines[-1].close)
        print(f"起始价格: {first_price:.2f}")
        print(f"结束价格: {last_price:.2f}")
        print(f"价格变化: {(last_price-first_price)/first_price*100:.2f}%")
        print(f"{'='*60}\n")
        
        initial_capital = 10000
        leverage = 3
        position_ratio = 0.5  # 使用50%资金
        amount_per_trade = (initial_capital * position_ratio * leverage) / first_price
        
        # 测试1: 只做多
        engine1 = RSIBollingerEngine(
            symbol="BTC-USDT-SWAP",
            initial_capital=initial_capital,
            rsi_period=14,
            rsi_oversold=35,  # 稍微放宽
            rsi_overbought=65,
            bollinger_period=20,
            bollinger_std=2.0,
            ema_period=50,
            amount_per_trade=amount_per_trade,
            fee_rate=0.0005,
            leverage=leverage,
            enable_short=False
        )
        
        for kline in klines:
            engine1.on_kline({
                'timestamp': kline.timestamp,
                'open': kline.open,
                'high': kline.high,
                'low': kline.low,
                'close': kline.close,
                'volume': kline.volume
            })
        
        final1 = engine1.capital
        if engine1.position.amount > 0:
            final1 += engine1.position.amount * last_price
        
        print(f"{'='*60}")
        print(f"测试1: RSI+布林带 - 只做多 (3倍杠杆)")
        print(f"{'='*60}")
        print(f"总收益率: {(final1-initial_capital)/initial_capital*100:.2f}%")
        print(f"最终资金: {final1:.2f} USDT")
        print(f"总盈亏: {final1-initial_capital:.2f} USDT")
        print(f"总交易次数: {len(engine1.trades)}")
        print(f"{'='*60}\n")
        
        # 测试2: 多空
        engine2 = RSIBollingerEngine(
            symbol="BTC-USDT-SWAP",
            initial_capital=initial_capital,
            rsi_period=14,
            rsi_oversold=35,
            rsi_overbought=65,
            bollinger_period=20,
            bollinger_std=2.0,
            ema_period=50,
            amount_per_trade=amount_per_trade,
            fee_rate=0.0005,
            leverage=leverage,
            enable_short=True
        )
        
        for kline in klines:
            engine2.on_kline({
                'timestamp': kline.timestamp,
                'open': kline.open,
                'high': kline.high,
                'low': kline.low,
                'close': kline.close,
                'volume': kline.volume
            })
        
        final2 = engine2.capital
        if engine2.position.amount != 0:
            if engine2.position.amount > 0:
                final2 += engine2.position.amount * last_price
            else:
                final2 += abs(engine2.position.amount) * last_price
        
        print(f"{'='*60}")
        print(f"测试2: RSI+布林带 - 多空 (3倍杠杆)")
        print(f"{'='*60}")
        print(f"总收益率: {(final2-initial_capital)/initial_capital*100:.2f}%")
        print(f"最终资金: {final2:.2f} USDT")
        print(f"总盈亏: {final2-initial_capital:.2f} USDT")
        print(f"总交易次数: {len(engine2.trades)}")
        print(f"{'='*60}\n")
        
        # 汇总
        print(f"{'='*60}")
        print(f"策略对比汇总")
        print(f"{'='*60}")
        print(f"{'策略':<25} {'收益率':>12} {'最终资金':>15} {'交易次数':>10}")
        print(f"{'-'*60}")
        print(f"{'RSI+BB只做多(3x)':<23} {(final1-initial_capital)/initial_capital*100:>11.2f}% {final1:>14.2f} {len(engine1.trades):>10}")
        print(f"{'RSI+BB多空(3x)':<23} {(final2-initial_capital)/initial_capital*100:>11.2f}% {final2:>14.2f} {len(engine2.trades):>10}")
        print(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


async def main():
    print("\n步骤1: 获取K线数据...")
    await fetch_klines()
    print("\n步骤2: 运行回测...")
    run_backtest()


if __name__ == "__main__":
    asyncio.run(main())
