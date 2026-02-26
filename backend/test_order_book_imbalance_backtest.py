"""
订单簿不平衡策略回测测试

使用K线数据回测订单簿不平衡策略的收益表现
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger

from app.services.backtest.metrics import BacktestMetrics


async def fetch_klines_from_okx(symbol: str, timeframe: str = "15m", days: int = 30):
    """
    从OKX获取K线数据
    
    Args:
        symbol: 交易对
        timeframe: 时间周期
        days: 获取多少天的数据
    """
    try:
        import aiohttp
        
        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # OKX API
        base_url = "https://www.okx.com"
        endpoint = "/api/v5/market/candles"
        
        klines = []
        limit = 300  # 每次最多300根
        after = None
        
        async with aiohttp.ClientSession() as session:
            while True:
                params = {
                    "instId": symbol,
                    "bar": timeframe,
                    "limit": str(limit)
                }
                if after:
                    params["after"] = after
                
                async with session.get(f"{base_url}{endpoint}", params=params) as resp:
                    data = await resp.json()
                    
                if data.get("code") != "0":
                    logger.error(f"获取K线失败: {data.get('msg')}")
                    break
                
                batch = data.get("data", [])
                if not batch:
                    break
                
                # 解析K线数据
                for item in batch:
                    # OKX格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                    kline = {
                        "timestamp": int(item[0]),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                    }
                    klines.append(kline)
                
                # 检查是否获取到足够的数据
                earliest_ts = int(batch[-1][0])
                if earliest_ts <= int(start_time.timestamp() * 1000):
                    break
                
                after = str(earliest_ts)
                
                logger.info(f"已获取 {len(klines)} 根K线...")
        
        # 按时间排序（从旧到新）
        klines.sort(key=lambda x: x["timestamp"])
        
        logger.info(f"总共获取 {len(klines)} 根K线")
        return klines
        
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return []


def generate_mock_klines(days: int = 30, interval_minutes: int = 15):
    """
    生成模拟K线数据（用于测试，当无法连接OKX时使用）
    
    模拟一个震荡上涨的市场环境
    """
    import random
    
    klines = []
    base_price = 3000.0  # ETH价格
    start_time = datetime.now() - timedelta(days=days)
    
    total_bars = days * 24 * 60 // interval_minutes
    
    for i in range(total_bars):
        timestamp = int((start_time + timedelta(minutes=i * interval_minutes)).timestamp() * 1000)
        
        # 随机波动
        change_pct = random.gauss(0.001, 0.015)  # 平均上涨0.1%，标准差1.5%
        
        if i > 0:
            base_price = klines[-1]["close"]
        
        # 生成OHLC
        open_price = base_price
        close_price = base_price * (1 + change_pct)
        
        # 高低价
        range_pct = abs(change_pct) + random.uniform(0.005, 0.02)
        high_price = max(open_price, close_price) * (1 + random.uniform(0, range_pct))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, range_pct))
        
        # 成交量
        volume = random.uniform(100, 500) * (1 + abs(change_pct) * 10)
        
        klines.append({
            "timestamp": timestamp,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 2),
        })
    
    logger.info(f"生成了 {len(klines)} 根模拟K线")
    return klines


def run_backtest(klines: list, params: dict):
    """运行回测"""
    logger.info("=" * 60)
    logger.info("开始回测订单簿不平衡策略")
    logger.info("=" * 60)
    
    # 创建回测引擎
    engine = OrderBookImbalanceBacktestEngine(
        symbol=params.get("symbol", "ETH-USDT-SWAP"),
        initial_capital=params.get("initial_capital", 10000),
        imbalance_threshold=params.get("imbalance_threshold", 0.25),
        min_imbalance_count=params.get("min_imbalance_count", 2),
        stop_loss=params.get("stop_loss", 0.003),
        take_profit=params.get("take_profit", 0.006),
        holding_bars=params.get("holding_bars", 4),
        cooldown_bars=params.get("cooldown_bars", 2),
        position_ratio=params.get("position_ratio", 0.3),
        leverage=params.get("leverage", 10),
        fee_rate=params.get("fee_rate", 0.0005),
    )
    
    # 运行回测
    logger.info(f"参数配置:")
    logger.info(f"  - 交易对: {params.get('symbol', 'ETH-USDT-SWAP')}")
    logger.info(f"  - 初始资金: ${params.get('initial_capital', 10000)}")
    logger.info(f"  - 不平衡阈值: ±{params.get('imbalance_threshold', 0.25) * 100}%")
    logger.info(f"  - 止损: {params.get('stop_loss', 0.003) * 100}%")
    logger.info(f"  - 止盈: {params.get('take_profit', 0.006) * 100}%")
    logger.info(f"  - 持仓K线数: {params.get('holding_bars', 4)}")
    logger.info(f"  - 杠杆: {params.get('leverage', 10)}x")
    logger.info("")
    
    for kline in klines:
        engine.on_kline(kline)
    
    # 获取结果
    stats = engine.get_stats()
    
    # 计算指标
    metrics = BacktestMetrics.calculate(
        equity_curve=engine.equity_curve,
        trades=engine.trades,
        initial_capital=params.get("initial_capital", 10000)
    )
    
    return stats, metrics, engine


def print_results(stats: dict, metrics: dict, engine):
    """打印回测结果"""
    print("\n")
    print("═" * 60)
    print("📊 回测结果")
    print("═" * 60)
    
    print(f"\n💰 收益指标:")
    print(f"  总收益率:     {stats['total_return']*100:>10.2f}%")
    print(f"  年化收益率:   {stats['annual_return']*100:>10.2f}%")
    print(f"  最终权益:     ${stats['final_equity']:>10.2f}")
    print(f"  最大回撤:     {stats['max_drawdown']*100:>10.2f}%")
    
    print(f"\n📈 交易统计:")
    print(f"  总交易次数:   {stats['total_trades']:>10}")
    print(f"  盈利次数:     {stats['win_trades']:>10}")
    print(f"  亏损次数:     {stats['lose_trades']:>10}")
    print(f"  胜率:         {stats['win_rate']*100:>10.2f}%")
    
    print(f"\n💵 盈亏分析:")
    print(f"  总盈亏:       ${stats['total_pnl']:>10.2f}")
    print(f"  平均盈利:     ${stats['avg_profit']:>10.2f}")
    print(f"  平均亏损:     ${stats['avg_loss']:>10.2f}")
    print(f"  盈亏比:       {stats['profit_factor']:>10.2f}")
    
    print(f"\n📊 风险指标:")
    print(f"  夏普比率:     {metrics.get('sharpe_ratio', 0):>10.2f}")
    print(f"  收益回撤比:   {metrics.get('calmar_ratio', 0):>10.2f}")
    print(f"  索提诺比率:   {metrics.get('sortino_ratio', 0):>10.2f}")
    
    # 不平衡度统计
    imb_stats = engine.get_imbalance_stats()
    print(f"\n📉 不平衡度统计:")
    print(f"  平均值:       {imb_stats['avg']:>10.4f}")
    print(f"  最大值:       {imb_stats['max']:>10.4f}")
    print(f"  最小值:       {imb_stats['min']:>10.4f}")
    
    # 最近几笔交易
    print(f"\n📋 最近5笔交易:")
    recent_trades = engine.trades[-5:] if engine.trades else []
    for i, trade in enumerate(recent_trades, 1):
        pnl_str = f"+{trade.pnl_percent*100:.2f}%" if trade.pnl_percent > 0 else f"{trade.pnl_percent*100:.2f}%"
        print(f"  {i}. {trade.side.upper():4} @ ${trade.price:.2f} | PnL: {pnl_str}")
    
    print("\n" + "═" * 60)


async def main():
    """主函数"""
    print("\n" + "🚀" * 25)
    print("订单簿不平衡策略回测测试")
    print("🚀" * 25 + "\n")
    
    # 尝试获取真实数据
    symbol = "ETH-USDT-SWAP"
    timeframe = "15m"
    days = 30
    
    logger.info(f"尝试获取 {symbol} {timeframe} 最近{days}天的K线数据...")
    
    klines = await fetch_klines_from_okx(symbol, timeframe, days)
    
    if not klines:
        logger.warning("无法获取真实数据，使用模拟数据进行测试...")
        klines = generate_mock_klines(days=days, interval_minutes=15)
    
    if not klines:
        logger.error("没有可用的K线数据")
        return
    
    # 回测参数
    params = {
        "symbol": symbol,
        "initial_capital": 10000,
        "imbalance_threshold": 0.25,
        "min_imbalance_count": 2,
        "stop_loss": 0.003,
        "take_profit": 0.006,
        "holding_bars": 4,
        "cooldown_bars": 2,
        "position_ratio": 0.3,
        "leverage": 10,
        "fee_rate": 0.0005,
    }
    
    # 运行回测
    stats, metrics, engine = run_backtest(klines, params)
    
    # 打印结果
    print_results(stats, metrics, engine)
    
    # 测试不同参数组合
    print("\n" + "🔄" * 25)
    print("参数敏感性分析")
    print("🔄" * 25 + "\n")
    
    param_sets = [
        {"name": "保守", "imbalance_threshold": 0.35, "stop_loss": 0.002, "take_profit": 0.004},
        {"name": "默认", "imbalance_threshold": 0.25, "stop_loss": 0.003, "take_profit": 0.006},
        {"name": "激进", "imbalance_threshold": 0.15, "stop_loss": 0.005, "take_profit": 0.010},
    ]
    
    results = []
    for pset in param_sets:
        test_params = params.copy()
        test_params.update(pset)
        name = test_params.pop("name")
        
        stats, _, _ = run_backtest(klines, test_params)
        results.append({
            "name": name,
            "total_return": stats["total_return"] * 100,
            "win_rate": stats["win_rate"] * 100,
            "max_drawdown": stats["max_drawdown"] * 100,
            "trades": stats["total_trades"],
        })
    
    print("\n📊 参数对比:")
    print("-" * 70)
    print(f"{'参数集':<8} {'总收益':>10} {'胜率':>10} {'最大回撤':>12} {'交易次数':>10}")
    print("-" * 70)
    for r in results:
        print(f"{r['name']:<8} {r['total_return']:>9.2f}% {r['win_rate']:>9.2f}% {r['max_drawdown']:>11.2f}% {r['trades']:>10}")
    print("-" * 70)


if __name__ == "__main__":
    asyncio.run(main())
