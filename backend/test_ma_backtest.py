"""
MA均线交叉策略回测测试脚本

测试MA策略在趋势市场中的表现
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from loguru import logger
from app.core.database import SessionLocal
from app.services.backtest.ma_cross_backtest import MACrossBacktestEngine
from app.services.backtest.metrics import BacktestMetrics
from app.models import Kline
from sqlalchemy import and_


def run_ma_backtest(
    symbol: str = "BTC-USDT",
    interval: str = "1H",
    days: int = 30,
    initial_capital: float = 10000,
    fast_period: int = 5,
    slow_period: int = 20,
    leverage: int = 1,
    enable_short: bool = False,
):
    """
    运行MA均线交叉策略回测
    
    Args:
        symbol: 交易对
        interval: K线周期
        days: 回测天数
        initial_capital: 初始资金
        fast_period: 快线周期
        slow_period: 慢线周期
        leverage: 杠杆倍数
        enable_short: 是否启用做空
    """
    print("\n" + "=" * 60)
    print(f"MA均线交叉策略回测测试")
    print("=" * 60)
    print(f"交易对: {symbol}")
    print(f"K线周期: {interval}")
    print(f"回测天数: {days}")
    print(f"初始资金: {initial_capital} USDT")
    print(f"快线周期: {fast_period}")
    print(f"慢线周期: {slow_period}")
    print(f"杠杆: {leverage}x")
    print(f"做空: {'启用' if enable_short else '禁用'}")
    print("=" * 60 + "\n")
    
    db = SessionLocal()
    try:
        # 直接从数据库获取K线数据
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        klines = db.query(Kline).filter(
            and_(
                Kline.symbol == symbol,
                Kline.interval == interval,
                Kline.timestamp >= start_ts,
                Kline.timestamp <= end_ts
            )
        ).order_by(Kline.timestamp.asc()).all()
        
        if not klines:
            print(f"错误: 没有找到K线数据")
            return None
        
        print(f"获取到 {len(klines)} 条K线数据")
        
        # 计算每笔交易数量(基于资金)
        first_price = float(klines[0].open)
        amount_per_trade = (initial_capital * 0.95) / first_price  # 使用95%资金
        
        # 创建回测引擎
        engine = MACrossBacktestEngine(
            symbol=symbol,
            initial_capital=initial_capital,
            fast_period=fast_period,
            slow_period=slow_period,
            ma_type="EMA",
            amount_per_trade=amount_per_trade,
            fee_rate=0.001,
            leverage=leverage,
            enable_short=enable_short
        )
        
        # 运行回测
        print("\n开始回测...")
        for kline in klines:
            engine.on_kline({
                'timestamp': kline.timestamp,
                'open': kline.open,
                'high': kline.high,
                'low': kline.low,
                'close': kline.close,
                'volume': kline.volume
            })
        
        # 获取结果
        final_capital = engine.capital
        if engine.position.amount != 0:
            # 平仓
            last_price = float(klines[-1].close)
            if engine.position.amount > 0:
                final_capital += engine.position.amount * last_price
            else:
                final_capital += abs(engine.position.amount) * last_price
        
        # 转换交易记录格式
        trades_data = []
        for t in engine.trades:
            trades_data.append({
                'side': t.side,
                'price': t.price,
                'amount': t.amount,
                'fee': t.fee,
                'pnl': t.pnl
            })
        
        # 获取时间戳范围
        start_ts = klines[0].timestamp if klines else 0
        end_ts = klines[-1].timestamp if klines else 0
        
        metrics = BacktestMetrics.calculate_all_metrics(
            initial_capital=initial_capital,
            final_capital=final_capital,
            equity_curve=engine.equity_curve,
            trades=trades_data,
            start_timestamp=start_ts,
            end_timestamp=end_ts
        )
        
        # 打印结果
        print("\n" + "=" * 60)
        print("回测结果")
        print("=" * 60)
        print(f"总收益率: {metrics['total_return']*100:.2f}%")
        print(f"年化收益率: {metrics['annualized_return']*100:.2f}%")
        print(f"最大回撤: {metrics['max_drawdown']*100:.2f}%")
        print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"胜率: {metrics['win_rate']*100:.2f}%")
        print(f"盈亏比: {metrics['profit_factor']:.2f}")
        print(f"总交易次数: {metrics['total_trades']}")
        print(f"盈利交易: {metrics['winning_trades']}")
        print(f"亏损交易: {metrics['losing_trades']}")
        print(f"最终资金: {final_capital:.2f} USDT")
        print(f"总盈亏: {final_capital - initial_capital:.2f} USDT")
        print("=" * 60 + "\n")
        
        return metrics
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


if __name__ == "__main__":
    # 测试1: 只做多
    print("\n" + "=" * 80)
    print("测试1: MA策略 - 只做多")
    print("=" * 80)
    run_ma_backtest(
        symbol="BTC-USDT",
        interval="1H",
        days=30,
        initial_capital=10000,
        fast_period=5,
        slow_period=20,
        leverage=1,
        enable_short=False
    )
    
    # 测试2: 做多+做空
    print("\n" + "=" * 80)
    print("测试2: MA策略 - 做多+做空")
    print("=" * 80)
    run_ma_backtest(
        symbol="BTC-USDT",
        interval="1H",
        days=30,
        initial_capital=10000,
        fast_period=5,
        slow_period=20,
        leverage=1,
        enable_short=True
    )
