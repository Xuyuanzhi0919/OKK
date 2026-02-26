"""
多维度策略验证器

在不同条件下验证优化后的参数：
- 不同回测天数：3天、7天、14天
- 不同K线周期：15m、1H、4H
- 不同交易对：BTC-USDT-SWAP、ETH-USDT-SWAP
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
import time


class TrendFollowEngine(BacktestEngine):
    """趋势跟踪策略"""
    
    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        fast_period: int = 7,
        slow_period: int = 30,
        amount_per_trade: float = 0.01,
        fee_rate: float = 0.0005,
        leverage: int = 3,
        stop_loss_percent: float = 0.01,
        take_profit_percent: float = 0.05,
    ):
        super().__init__(
            symbol=symbol,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            leverage=leverage,
            enable_short=False
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


async def fetch_klines_for_symbol(symbol: str, interval: str, days: int):
    """获取指定交易对的K线数据"""
    from app.services.exchange.okx import OKXExchange
    from app.services.backtest.kline_service import KlineService
    
    db = SessionLocal()
    try:
        exchange = OKXExchange(api_key="", secret_key="", passphrase="", simulated=True)
        kline_service = KlineService(db, exchange)
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        result = await kline_service.fetch_and_save_klines(
            symbol=symbol,
            interval=interval,
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000)
        )
        
        await exchange.close()
        return result
    except Exception as e:
        logger.error(f"获取{symbol} {interval} K线失败: {e}")
        return None
    finally:
        db.close()


def run_backtest_for_config(symbol: str, interval: str, days: int, leverage: int = 3):
    """运行单个配置的回测"""
    db = SessionLocal()
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        klines = db.query(Kline).filter(
            and_(
                Kline.symbol == symbol,
                Kline.interval == interval,
                Kline.timestamp >= int(start_time.timestamp() * 1000),
                Kline.timestamp <= int(end_time.timestamp() * 1000)
            )
        ).order_by(Kline.timestamp.asc()).all()
        
        if not klines:
            return None
        
        first_price = float(klines[0].open)
        last_price = float(klines[-1].close)
        price_change = (last_price - first_price) / first_price * 100
        
        initial_capital = 10000
        position_ratio = 0.4
        amount_per_trade = (initial_capital * position_ratio * leverage) / first_price
        
        # 使用优化后的参数
        engine = TrendFollowEngine(
            symbol=symbol,
            initial_capital=initial_capital,
            fast_period=7,
            slow_period=30,
            amount_per_trade=amount_per_trade,
            fee_rate=0.0005,
            leverage=leverage,
            stop_loss_percent=0.01,
            take_profit_percent=0.05,
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
        
        return {
            'symbol': symbol,
            'interval': interval,
            'days': days,
            'klines': len(klines),
            'price_change': price_change,
            'return': total_return,
            'trades': len(engine.trades),
            'win_rate': win_rate,
            'final': final
        }
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        return None
    finally:
        db.close()


async def main():
    print("\n" + "=" * 80)
    print("多维度策略验证器")
    print("=" * 80)
    
    # 测试配置
    symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    intervals = ["15m", "1H", "4H"]
    days_list = [3, 7, 14]
    
    results = []
    
    total_configs = len(symbols) * len(intervals) * len(days_list)
    current = 0
    
    for symbol in symbols:
        for interval in intervals:
            for days in days_list:
                current += 1
                print(f"\n[{current}/{total_configs}] 测试: {symbol} | {interval} | {days}天")
                
                # 获取数据
                print(f"  获取K线数据...")
                await fetch_klines_for_symbol(symbol, interval, days)
                
                # 等待一下避免请求过快
                await asyncio.sleep(0.5)
                
                # 运行回测
                print(f"  运行回测...")
                result = run_backtest_for_config(symbol, interval, days)
                
                if result:
                    results.append(result)
                    print(f"  完成: 收益率={result['return']:.2f}%, 胜率={result['win_rate']:.1f}%, 交易={result['trades']}")
                else:
                    print(f"  失败: 无数据")
    
    # 输出结果汇总
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    print(f"\n{'交易对':<18} {'周期':<6} {'天数':<6} {'K线数':<8} {'价格变化':>10} {'收益率':>10} {'胜率':>8} {'交易':>6}")
    print("-" * 80)
    
    for r in results:
        print(f"{r['symbol']:<18} {r['interval']:<6} {r['days']:<6} {r['klines']:<8} "
              f"{r['price_change']:>9.2f}% {r['return']:>9.2f}% {r['win_rate']:>7.1f}% {r['trades']:>6}")
    
    # 按交易对汇总
    print("\n" + "=" * 80)
    print("按交易对汇总")
    print("=" * 80)
    
    for symbol in symbols:
        symbol_results = [r for r in results if r['symbol'] == symbol]
        if symbol_results:
            avg_return = sum(r['return'] for r in symbol_results) / len(symbol_results)
            avg_win_rate = sum(r['win_rate'] for r in symbol_results) / len(symbol_results)
            total_trades = sum(r['trades'] for r in symbol_results)
            profitable = sum(1 for r in symbol_results if r['return'] > 0)
            
            print(f"\n{symbol}:")
            print(f"  平均收益率: {avg_return:.2f}%")
            print(f"  平均胜率: {avg_win_rate:.1f}%")
            print(f"  总交易次数: {total_trades}")
            print(f"  盈利配置: {profitable}/{len(symbol_results)}")
    
    # 按K线周期汇总
    print("\n" + "=" * 80)
    print("按K线周期汇总")
    print("=" * 80)
    
    for interval in intervals:
        interval_results = [r for r in results if r['interval'] == interval]
        if interval_results:
            avg_return = sum(r['return'] for r in interval_results) / len(interval_results)
            avg_win_rate = sum(r['win_rate'] for r in interval_results) / len(interval_results)
            profitable = sum(1 for r in interval_results if r['return'] > 0)
            
            print(f"\n{interval}:")
            print(f"  平均收益率: {avg_return:.2f}%")
            print(f"  平均胜率: {avg_win_rate:.1f}%")
            print(f"  盈利配置: {profitable}/{len(interval_results)}")
    
    # 按回测天数汇总
    print("\n" + "=" * 80)
    print("按回测天数汇总")
    print("=" * 80)
    
    for days in days_list:
        days_results = [r for r in results if r['days'] == days]
        if days_results:
            avg_return = sum(r['return'] for r in days_results) / len(days_results)
            avg_win_rate = sum(r['win_rate'] for r in days_results) / len(days_results)
            profitable = sum(1 for r in days_results if r['return'] > 0)
            
            print(f"\n{days}天:")
            print(f"  平均收益率: {avg_return:.2f}%")
            print(f"  平均胜率: {avg_win_rate:.1f}%")
            print(f"  盈利配置: {profitable}/{len(days_results)}")
    
    print("\n" + "=" * 80)
    print("验证完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
