"""
策略参数优化器

自动寻找最佳的EMA周期、止损止盈参数
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from datetime import datetime, timedelta
from loguru import logger
from typing import List, Dict
from itertools import product
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
        stop_loss_percent: float = 0.02,
        take_profit_percent: float = 0.04,
    ):
        super().__init__(
            symbol=symbol,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            leverage=leverage,
            enable_short=False  # 只做多
        )
        
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.amount_per_trade = amount_per_trade
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent
        
        self.price_history: List[float] = []
        self.fast_ema_history: List[float] = []
        self.slow_ema_history: List[float] = []
        self.entry_price: float = 0
    
    def reset(self):
        super().reset()
        self.price_history = []
        self.fast_ema_history = []
        self.slow_ema_history = []
        self.entry_price = 0
    
    def calculate_ema(self, prices: List[float], period: int, prev_ema: float = None) -> float:
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
        timestamp = int(kline['timestamp'])
        close_price = float(kline['close'])
        high_price = float(kline['high'])
        low_price = float(kline['low'])
        
        self.price_history.append(close_price)
        self.current_kline = kline
        
        prev_fast = self.fast_ema_history[-1] if self.fast_ema_history else None
        prev_slow = self.slow_ema_history[-1] if self.slow_ema_history else None
        
        fast_ema = self.calculate_ema(self.price_history, self.fast_period, prev_fast)
        slow_ema = self.calculate_ema(self.price_history, self.slow_period, prev_slow)
        
        self.fast_ema_history.append(fast_ema)
        self.slow_ema_history.append(slow_ema)
        
        if len(self.price_history) < self.slow_period + 2:
            return
        
        prev_fast = self.fast_ema_history[-2]
        prev_slow = self.slow_ema_history[-2]
        
        has_long = self.position.amount > 0
        
        # 止损止盈
        if has_long and self.entry_price > 0:
            pnl_percent = (close_price - self.entry_price) / self.entry_price
            if pnl_percent <= -self.stop_loss_percent:
                self.sell(close_price, self.amount_per_trade, timestamp)
                self.entry_price = 0
                return
            elif pnl_percent >= self.take_profit_percent:
                self.sell(close_price, self.amount_per_trade, timestamp)
                self.entry_price = 0
                return
        
        golden_cross = prev_fast <= prev_slow and fast_ema > slow_ema
        death_cross = prev_fast >= prev_slow and fast_ema < slow_ema
        
        if not has_long and golden_cross:
            trade = self.buy(close_price, self.amount_per_trade, timestamp)
            if trade:
                self.entry_price = close_price
        
        elif has_long and death_cross:
            trade = self.sell(close_price, self.amount_per_trade, timestamp)
            if trade:
                self.entry_price = 0


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


def run_optimization():
    """运行参数优化"""
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
        
        print(f"\n{'='*70}")
        print(f"策略参数优化器")
        print(f"{'='*70}")
        print(f"交易对: BTC-USDT-SWAP")
        print(f"K线周期: 15分钟")
        print(f"回测天数: 3天")
        print(f"初始资金: 10000 USDT")
        print(f"杠杆: 3x")
        print(f"价格变化: {(last_price-first_price)/first_price*100:.2f}%")
        print(f"{'='*70}\n")
        
        initial_capital = 10000
        leverage = 3
        position_ratio = 0.4
        amount_per_trade = (initial_capital * position_ratio * leverage) / first_price
        
        # 参数范围
        fast_periods = [2, 3, 5, 7]
        slow_periods = [10, 15, 20, 25, 30]
        stop_loss_percents = [0.01, 0.02, 0.03, 0.05]  # 1%, 2%, 3%, 5%
        take_profit_percents = [0.02, 0.03, 0.05, 0.08, 0.10]  # 2%, 3%, 5%, 8%, 10%
        
        results = []
        total_combinations = len(fast_periods) * len(slow_periods) * len(stop_loss_percents) * len(take_profit_percents)
        
        print(f"参数组合总数: {total_combinations}")
        print(f"开始优化...\n")
        
        count = 0
        for fast, slow, sl, tp in product(fast_periods, slow_periods, stop_loss_percents, take_profit_percents):
            if fast >= slow:
                continue
            
            count += 1
            if count % 20 == 0:
                print(f"进度: {count}/{total_combinations}")
            
            engine = TrendFollowEngine(
                symbol="BTC-USDT-SWAP",
                initial_capital=initial_capital,
                fast_period=fast,
                slow_period=slow,
                amount_per_trade=amount_per_trade,
                fee_rate=0.0005,
                leverage=leverage,
                stop_loss_percent=sl,
                take_profit_percent=tp,
            )
            
            for kline in klines:
                engine.on_kline({
                    'timestamp': kline.timestamp,
                    'open': kline.open,
                    'high': kline.high,
                    'low': kline.low,
                    'close': kline.close,
                    'volume': kline.volume
                })
            
            # 计算最终资金
            final = engine.capital
            if engine.position.amount > 0:
                margin = engine.position.amount * engine.position.avg_price / leverage
                unrealized_pnl = (last_price - engine.position.avg_price) * engine.position.amount
                final = engine.capital + margin + unrealized_pnl
            
            total_return = (final - initial_capital) / initial_capital * 100
            
            # 计算胜率
            sell_trades = [t for t in engine.trades if t.side == 'sell']
            wins = sum(1 for t in sell_trades if t.pnl > 0)
            win_rate = wins / len(sell_trades) * 100 if sell_trades else 0
            
            # 计算盈亏比
            total_profit = sum(t.pnl for t in sell_trades if t.pnl > 0)
            total_loss = abs(sum(t.pnl for t in sell_trades if t.pnl < 0))
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            results.append({
                'fast': fast,
                'slow': slow,
                'stop_loss': sl * 100,
                'take_profit': tp * 100,
                'return': total_return,
                'trades': len(engine.trades),
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'final': final
            })
        
        # 按收益率排序
        results.sort(key=lambda x: x['return'], reverse=True)
        
        # 输出Top 10
        print(f"\n{'='*70}")
        print(f"Top 10 最佳参数组合")
        print(f"{'='*70}")
        print(f"{'排名':<4} {'快线':<4} {'慢线':<4} {'止损%':<6} {'止盈%':<6} {'收益率':<8} {'交易':<6} {'胜率':<8} {'盈亏比':<8}")
        print(f"{'-'*70}")
        
        for i, r in enumerate(results[:10]):
            print(f"{i+1:<4} {r['fast']:<4} {r['slow']:<4} {r['stop_loss']:<6.1f} {r['take_profit']:<6.1f} "
                  f"{r['return']:>7.2f}% {r['trades']:<6} {r['win_rate']:>7.1f}% {r['profit_factor']:>7.2f}")
        
        print(f"{'='*70}")
        
        # 最佳参数
        best = results[0]
        print(f"\n最佳参数:")
        print(f"  快线EMA周期: {best['fast']}")
        print(f"  慢线EMA周期: {best['slow']}")
        print(f"  止损: {best['stop_loss']:.1f}%")
        print(f"  止盈: {best['take_profit']:.1f}%")
        print(f"  收益率: {best['return']:.2f}%")
        print(f"  胜率: {best['win_rate']:.1f}%")
        print(f"  盈亏比: {best['profit_factor']:.2f}")
        
        return results
        
    except Exception as e:
        logger.error(f"优化失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


async def main():
    print("\n步骤1: 获取K线数据...")
    await fetch_klines()
    print("\n步骤2: 运行参数优化...")
    run_optimization()


if __name__ == "__main__":
    asyncio.run(main())
