"""
3天15分钟K线3倍杠杆回测测试

1. 先获取15分钟K线数据
2. 运行MA策略回测(3倍杠杆)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from datetime import datetime, timedelta
from loguru import logger
from app.core.database import SessionLocal
from app.services.backtest.ma_cross_backtest import MACrossBacktestEngine
from app.services.backtest.metrics import BacktestMetrics
from app.models import Kline
from sqlalchemy import and_


async def fetch_15m_klines():
    """获取15分钟K线数据"""
    from app.services.exchange.okx import OKXExchange
    from app.services.backtest.kline_service import KlineService
    
    db = SessionLocal()
    try:
        # 创建交易所实例
        exchange = OKXExchange(
            api_key="",
            secret_key="",
            passphrase="",
            simulated=True
        )
        
        kline_service = KlineService(db, exchange)
        
        # 获取最近3天的数据
        end_time = datetime.now()
        start_time = end_time - timedelta(days=3)
        
        # 使用永续合约交易对 BTC-USDT-SWAP
        result = await kline_service.fetch_and_save_klines(
            symbol="BTC-USDT-SWAP",  # 永续合约
            interval="15m",
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000)
        )
        
        print(f"获取K线数据完成: {result}")
        await exchange.close()
        return result
        
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


def run_backtest():
    """运行回测"""
    db = SessionLocal()
    try:
        # 获取K线数据
        end_time = datetime.now()
        start_time = end_time - timedelta(days=3)
        
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        # 使用永续合约交易对
        klines = db.query(Kline).filter(
            and_(
                Kline.symbol == "BTC-USDT-SWAP",  # 永续合约
                Kline.interval == "15m",
                Kline.timestamp >= start_ts,
                Kline.timestamp <= end_ts
            )
        ).order_by(Kline.timestamp.asc()).all()
        
        if not klines:
            print("错误: 没有15分钟K线数据，请先获取")
            return None
        
        print(f"获取到 {len(klines)} 条15分钟K线数据")
        
        # 计算参数
        first_price = float(klines[0].open)
        last_price = float(klines[-1].close)
        initial_capital = 10000
        
        # 3倍杠杆，每次交易使用30%的保证金
        # 仓位价值 = 保证金 * 杠杆，所以数量 = (资金*比例*杠杆) / 价格
        leverage = 3
        position_ratio = 0.3  # 每次使用30%资金
        amount_per_trade = (initial_capital * position_ratio * leverage) / first_price
        
        print(f"\n{'='*60}")
        print(f"MA均线交叉策略 - 3倍杠杆合约回测")
        print(f"{'='*60}")
        print(f"交易对: BTC-USDT-SWAP (永续合约)")
        print(f"K线周期: 15分钟")
        print(f"回测天数: 3天")
        print(f"初始资金: {initial_capital} USDT")
        print(f"杠杆: {leverage}x")
        print(f"起始价格: {first_price:.2f}")
        print(f"结束价格: {last_price:.2f}")
        print(f"价格变化: {(last_price-first_price)/first_price*100:.2f}%")
        print(f"{'='*60}\n")
        
        # 测试1: 只做多
        engine1 = MACrossBacktestEngine(
            symbol="BTC-USDT-SWAP",  # 永续合约
            initial_capital=initial_capital,
            fast_period=5,
            slow_period=20,
            ma_type="EMA",
            amount_per_trade=amount_per_trade,
            fee_rate=0.0005,  # 合约手续费更低
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
        print(f"测试1: MA策略 - 只做多 (3倍杠杆)")
        print(f"{'='*60}")
        print(f"总收益率: {(final1-initial_capital)/initial_capital*100:.2f}%")
        print(f"最终资金: {final1:.2f} USDT")
        print(f"总盈亏: {final1-initial_capital:.2f} USDT")
        print(f"总交易次数: {len(engine1.trades)}")
        print(f"{'='*60}\n")
        
        # 测试2: 做多+做空
        engine2 = MACrossBacktestEngine(
            symbol="BTC-USDT-SWAP",  # 永续合约
            initial_capital=initial_capital,
            fast_period=5,
            slow_period=20,
            ma_type="EMA",
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
        print(f"测试2: MA策略 - 做多+做空 (3倍杠杆)")
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
        print(f"{'策略':<20} {'收益率':>12} {'最终资金':>15} {'交易次数':>10}")
        print(f"{'-'*60}")
        print(f"{'MA只做多(3x)':<18} {(final1-initial_capital)/initial_capital*100:>11.2f}% {final1:>14.2f} {len(engine1.trades):>10}")
        print(f"{'MA多空(3x)':<18} {(final2-initial_capital)/initial_capital*100:>11.2f}% {final2:>14.2f} {len(engine2.trades):>10}")
        print(f"{'='*60}")
        
        return {
            "long_only": {"final": final1, "return": (final1-initial_capital)/initial_capital*100},
            "long_short": {"final": final2, "return": (final2-initial_capital)/initial_capital*100}
        }
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("步骤1: 获取15分钟K线数据")
    print("="*60 + "\n")
    
    result = await fetch_15m_klines()
    
    if result:
        print("\n" + "="*60)
        print("步骤2: 运行回测")
        print("="*60 + "\n")
        run_backtest()
    else:
        print("获取K线数据失败，无法运行回测")


if __name__ == "__main__":
    asyncio.run(main())
