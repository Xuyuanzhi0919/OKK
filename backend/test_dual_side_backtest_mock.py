"""
双向持仓策略回测对比测试（使用模拟数据）

对比1分钟、5分钟、15分钟周期的回测效果
"""
import asyncio
import sys
import os
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger


def generate_mock_klines(base_price: float, count: int, volatility: float = 0.02) -> list:
    """
    生成模拟K线数据
    
    Args:
        base_price: 基础价格
        count: K线数量
        volatility: 波动率
    
    Returns:
        K线列表
    """
    klines = []
    price = base_price
    timestamp = int((datetime.now() - timedelta(minutes=count)).timestamp() * 1000)
    
    # 创建趋势：先上涨后下跌
    trend = 1  # 1=上涨, -1=下跌
    
    for i in range(count):
        # 每500根K线切换趋势
        if i > 0 and i % 500 == 0:
            trend *= -1
        
        # 生成OHLCV
        change = random.uniform(-volatility, volatility) + trend * 0.001
        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + random.uniform(0, volatility/2))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, volatility/2))
        volume = random.uniform(100, 1000)
        
        klines.append({
            "timestamp": timestamp + i * 60000,  # 1分钟间隔
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })
        
        price = close_price
    
    return klines


async def run_backtest_comparison():
    """运行回测对比"""
    from app.services.backtest.dual_side_backtest import DualSideBacktestEngine
    
    symbol = "BTC-USDT-SWAP"
    
    # 生成模拟数据（模拟7天的1分钟K线，约10000根）
    logger.info("正在生成模拟K线数据...")
    base_price = 80000  # BTC价格
    all_klines = generate_mock_klines(base_price, 10000, volatility=0.015)
    logger.info(f"生成 {len(all_klines)} 根模拟K线")
    
    results = {}
    
    # 测试不同周期
    intervals = [
        ("1m", 1),      # 1分钟，每根K线
        ("5m", 5),      # 5分钟，每5根K线
        ("15m", 15),    # 15分钟，每15根K线
    ]
    
    for interval_name, skip in intervals:
        logger.info(f"\n{'='*50}")
        logger.info(f"回测 {symbol} {interval_name}")
        logger.info(f"{'='*50}")
        
        try:
            # 按周期采样K线
            klines = all_klines[::skip]
            logger.info(f"采样后K线数量: {len(klines)}")
            
            # 创建回测引擎
            engine = DualSideBacktestEngine(
                symbol=symbol,
                initial_capital=1000,
                fast_period=12,
                slow_period=40,
                position_ratio=0.3,
                leverage=5,
                stop_loss=0.02,
                take_profit=0.06,
                trailing_stop=0.02,
                fee_rate=0.001
            )
            
            # 运行回测
            logger.info("正在运行回测...")
            for kline in klines:
                engine.on_kline(kline)
            
            # 获取结果
            stats = engine.get_statistics()
            results[interval_name] = stats
            
            logger.info(f"总收益率: {stats['total_return_pct']:.2f}%")
            logger.info(f"最大回撤: {stats['max_drawdown_pct']:.2f}%")
            logger.info(f"胜率: {stats['win_rate']:.1f}%")
            logger.info(f"交易次数: {stats['total_trades']}")
            logger.info(f"盈亏比: {stats['profit_factor']:.2f}")
            
        except Exception as e:
            logger.error(f"回测失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 对比结果
    print("\n" + "="*90)
    print("📊 双向持仓策略回测对比结果（模拟数据）")
    print("="*90)
    print(f"{'周期':<10} {'收益率':<14} {'最大回撤':<14} {'胜率':<12} {'交易次数':<12} {'盈亏比':<12}")
    print("-"*90)
    
    best_interval = None
    best_return = -float('inf')
    
    for interval_name, _ in intervals:
        if interval_name in results:
            r = results[interval_name]
            print(f"{interval_name:<10} {r['total_return_pct']:>12.2f}% {r['max_drawdown_pct']:>12.2f}% {r['win_rate']:>10.1f}% {r['total_trades']:>12} {r['profit_factor']:>12.2f}")
            
            if r['total_return_pct'] > best_return:
                best_return = r['total_return_pct']
                best_interval = interval_name
    
    print("="*90)
    if best_interval:
        print(f"✅ 推荐周期: {best_interval} (收益率: {best_return:.2f}%)")
        print(f"\n说明:")
        print(f"  - 1分钟周期: 信号多但噪音大，手续费影响大")
        print(f"  - 5分钟周期: 信号适中，噪音较小")
        print(f"  - 15分钟周期: 信号质量高，趋势跟踪效果好（推荐）")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_backtest_comparison())
