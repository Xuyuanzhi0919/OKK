"""
趋势跟踪策略 - 更激进的参数

策略逻辑：
1. 使用快速EMA(3)和慢速EMA(7)交叉
2. 价格在两条EMA上方时只做多
3. 价格在两条EMA下方时只做空
4. 使用更小的仓位，更频繁的交易
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from datetime import datetime, timedelta
from loguru import logger
from typing import List, Dict
from app.core.database import SessionLocal
from app.services.backtest.backtest_engine import BacktestEngine
from app.models import Kline
from sqlalchemy import and_


class TrendFollowEngine(BacktestEngine):
    """趋势跟踪策略"""
    
    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        fast_period: int = 3,
        slow_period: int = 7,
        amount_per_trade: float = 0.01,
        fee_rate: float = 0.0005,
        leverage: int = 3,
        enable_short: bool = True,
        stop_loss_percent: float = 0.02,  # 2%止损
        take_profit_percent: float = 0.04,  # 4%止盈
    ):
        super().__init__(
            symbol=symbol,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            leverage=leverage,
            enable_short=enable_short
        )
        
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.amount_per_trade = amount_per_trade
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent
        
        self.price_history: List[float] = []
        self.fast_ema_history: List[float] = []
        self.slow_ema_history: List[float] = []
        
        # 记录入场价格
        self.entry_price: float = 0
        
        logger.info(f"趋势跟踪策略: 快线={fast_period}, 慢线={slow_period}, 止损={stop_loss_percent*100}%, 止盈={take_profit_percent*100}%")
    
    def calculate_ema(self, prices: List[float], period: int, prev_ema: float = None) -> float:
        """计算EMA"""
        if not prices:
            return 0
        if len(prices) < period:
            return sum(prices) / len(prices)
        
        multiplier = 2 / (period + 1)
        
        if prev_ema is None:
            ema = sum(prices[:period]) / period
            for price in prices[period:]:
                ema = (price - ema) * multiplier + ema
        else:
            ema = (prices[-1] - prev_ema) * multiplier + prev_ema
        
        return ema
    
    def on_kline(self, kline: Dict):
        """处理K线"""
        timestamp = int(kline['timestamp'])
        close_price = float(kline['close'])
        high_price = float(kline['high'])
        low_price = float(kline['low'])
        
        self.price_history.append(close_price)
        self.current_kline = kline
        
        # 计算EMA
        prev_fast = self.fast_ema_history[-1] if self.fast_ema_history else None
        prev_slow = self.slow_ema_history[-1] if self.slow_ema_history else None
        
        fast_ema = self.calculate_ema(self.price_history, self.fast_period, prev_fast)
        slow_ema = self.calculate_ema(self.price_history, self.slow_period, prev_slow)
        
        self.fast_ema_history.append(fast_ema)
        self.slow_ema_history.append(slow_ema)
        
        # 需要足够数据
        if len(self.price_history) < self.slow_period + 2:
            return
        
        prev_fast = self.fast_ema_history[-2]
        prev_slow = self.slow_ema_history[-2]
        
        has_long = self.position.amount > 0
        has_short = self.position.amount < 0
        
        # 止损止盈检查
        if has_long and self.entry_price > 0:
            pnl_percent = (close_price - self.entry_price) / self.entry_price
            if pnl_percent <= -self.stop_loss_percent:
                self.sell(close_price, self.amount_per_trade, timestamp)
                self.entry_price = 0
                logger.debug(f"止损平多: 盈亏={pnl_percent*100:.2f}%")
                return
            elif pnl_percent >= self.take_profit_percent:
                self.sell(close_price, self.amount_per_trade, timestamp)
                self.entry_price = 0
                logger.debug(f"止盈平多: 盈亏={pnl_percent*100:.2f}%")
                return
        
        if has_short and self.entry_price > 0:
            pnl_percent = (self.entry_price - close_price) / self.entry_price
            if pnl_percent <= -self.stop_loss_percent:
                self.cover(close_price, self.amount_per_trade, timestamp)
                self.entry_price = 0
                logger.debug(f"止损平空: 盈亏={pnl_percent*100:.2f}%")
                return
            elif pnl_percent >= self.take_profit_percent:
                self.cover(close_price, self.amount_per_trade, timestamp)
                self.entry_price = 0
                logger.debug(f"止盈平空: 盈亏={pnl_percent*100:.2f}%")
                return
        
        # 金叉死叉判断
        golden_cross = prev_fast <= prev_slow and fast_ema > slow_ema
        death_cross = prev_fast >= prev_slow and fast_ema < slow_ema
        
        # 交易逻辑
        if not has_long and not has_short:
            if golden_cross:
                trade = self.buy(close_price, self.amount_per_trade, timestamp)
                if trade:
                    self.entry_price = close_price
                    logger.debug(f"金叉开多: 价格={close_price:.2f}")
            
            elif self.enable_short and death_cross:
                trade = self.short(close_price, self.amount_per_trade, timestamp)
                if trade:
                    self.entry_price = close_price
                    logger.debug(f"死叉开空: 价格={close_price:.2f}")
        
        elif has_long and death_cross:
            trade = self.sell(close_price, self.amount_per_trade, timestamp)
            if trade:
                self.entry_price = 0
                logger.debug(f"死叉平多: 盈亏={trade.pnl:.2f}")
        
        elif has_short and golden_cross:
            trade = self.cover(close_price, self.amount_per_trade, timestamp)
            if trade:
                self.entry_price = 0
                logger.debug(f"金叉平空: 盈亏={trade.pnl:.2f}")


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
        
        first_price = float(klines[0].open)
        last_price = float(klines[-1].close)
        
        print(f"\n{'='*60}")
        print(f"趋势跟踪策略 - 3倍杠杆合约回测")
        print(f"{'='*60}")
        print(f"交易对: BTC-USDT-SWAP")
        print(f"K线周期: 15分钟")
        print(f"回测天数: 3天")
        print(f"初始资金: 10000 USDT")
        print(f"杠杆: 3x")
        print(f"起始价格: {first_price:.2f}")
        print(f"结束价格: {last_price:.2f}")
        print(f"价格变化: {(last_price-first_price)/first_price*100:.2f}%")
        print(f"{'='*60}\n")
        
        initial_capital = 10000
        leverage = 3
        position_ratio = 0.4  # 40%资金
        amount_per_trade = (initial_capital * position_ratio * leverage) / first_price
        
        # 测试1: 只做多，2%止损4%止盈
        engine1 = TrendFollowEngine(
            symbol="BTC-USDT-SWAP",
            initial_capital=initial_capital,
            fast_period=3,
            slow_period=7,
            amount_per_trade=amount_per_trade,
            fee_rate=0.0005,
            leverage=leverage,
            enable_short=False,
            stop_loss_percent=0.02,
            take_profit_percent=0.04,
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
            # 多头：资金 + 保证金 + 未实现盈亏
            margin = engine1.position.amount * engine1.position.avg_price / leverage
            unrealized_pnl = (last_price - engine1.position.avg_price) * engine1.position.amount
            final1 = engine1.capital + margin + unrealized_pnl
        
        # 计算胜率
        sell_trades = [t for t in engine1.trades if t.side == 'sell']
        wins = sum(1 for t in sell_trades if t.pnl > 0)
        win_rate = wins / len(sell_trades) * 100 if sell_trades else 0
        
        print(f"{'='*60}")
        print(f"测试1: 趋势跟踪 - 只做多 (3x杠杆, 2%止损, 4%止盈)")
        print(f"{'='*60}")
        print(f"总收益率: {(final1-initial_capital)/initial_capital*100:.2f}%")
        print(f"最终资金: {final1:.2f} USDT")
        print(f"总盈亏: {final1-initial_capital:.2f} USDT")
        print(f"总交易次数: {len(engine1.trades)}")
        print(f"胜率: {win_rate:.1f}%")
        print(f"{'='*60}\n")
        
        # 测试2: 多空
        engine2 = TrendFollowEngine(
            symbol="BTC-USDT-SWAP",
            initial_capital=initial_capital,
            fast_period=3,
            slow_period=7,
            amount_per_trade=amount_per_trade,
            fee_rate=0.0005,
            leverage=leverage,
            enable_short=True,
            stop_loss_percent=0.02,
            take_profit_percent=0.04,
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
                # 多头：资金 + 持仓价值
                final2 += engine2.position.amount * last_price
            else:
                # 空头：资金 + 保证金 + 未实现盈亏
                margin = abs(engine2.position.amount) * engine2.position.avg_price / leverage
                unrealized_pnl = (engine2.position.avg_price - last_price) * abs(engine2.position.amount)
                final2 = engine2.capital + margin + unrealized_pnl
        
        sell_trades2 = [t for t in engine2.trades if t.side == 'sell']
        wins2 = sum(1 for t in sell_trades2 if t.pnl > 0)
        win_rate2 = wins2 / len(sell_trades2) * 100 if sell_trades2 else 0
        
        print(f"{'='*60}")
        print(f"测试2: 趋势跟踪 - 多空 (3x杠杆, 2%止损, 4%止盈)")
        print(f"{'='*60}")
        print(f"总收益率: {(final2-initial_capital)/initial_capital*100:.2f}%")
        print(f"最终资金: {final2:.2f} USDT")
        print(f"总盈亏: {final2-initial_capital:.2f} USDT")
        print(f"总交易次数: {len(engine2.trades)}")
        print(f"胜率: {win_rate2:.1f}%")
        print(f"{'='*60}\n")
        
        # 汇总
        print(f"{'='*60}")
        print(f"策略对比汇总")
        print(f"{'='*60}")
        print(f"{'策略':<25} {'收益率':>12} {'最终资金':>15} {'交易':>8} {'胜率':>8}")
        print(f"{'-'*60}")
        print(f"{'趋势跟踪只做多(3x)':<21} {(final1-initial_capital)/initial_capital*100:>11.2f}% {final1:>14.2f} {len(engine1.trades):>8} {win_rate:>7.1f}%")
        print(f"{'趋势跟踪多空(3x)':<21} {(final2-initial_capital)/initial_capital*100:>11.2f}% {final2:>14.2f} {len(engine2.trades):>8} {win_rate2:>7.1f}%")
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
