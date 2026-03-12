"""
双向持仓策略回测对比测试

对比不同时间周期（1m、5m、15m）的回测效果
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger


async def fetch_klines_from_okx(symbol: str, interval: str, days: int = 7):
    """从OKX获取K线数据"""
    import aiohttp
    
    # OKX K线API
    url = f"https://www.okx.com/api/v5/market/candles"
    
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    # 转换为毫秒时间戳
    after = int(start_time.timestamp() * 1000)
    before = int(end_time.timestamp() * 1000)
    
    all_klines = []
    limit = 300  # OKX单次最多300根
    
    async with aiohttp.ClientSession() as session:
        current_after = after
        while current_after < before:
            params = {
                "instId": symbol,
                "bar": interval,
                "after": current_after,
                "before": before,
                "limit": limit
            }
            
            try:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    
                    if data.get("code") != "0":
                        logger.error(f"API错误: {data.get('msg')}")
                        break
                    
                    klines = data.get("data", [])
                    if not klines:
                        break
                    
                    # OKX返回格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                    for k in klines:
                        all_klines.append({
                            "timestamp": int(k[0]),
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                        })
                    
                    # 更新游标（OKX返回的是倒序，最后一根是最早的）
                    if len(klines) < limit:
                        break
                    current_after = int(klines[-1][0]) - 1
                    
            except Exception as e:
                logger.error(f"请求失败: {e}")
                break
    
    # 按时间正序排列
    all_klines.sort(key=lambda x: x["timestamp"])
    return all_klines


async def run_backtest_comparison():
    """运行回测对比"""
    from app.services.backtest.dual_side_backtest import DualSideBacktestEngine
    
    symbol = "BTC-USDT-SWAP"
    intervals = ["1m", "5m", "15m"]
    
    results = {}
    
    for interval in intervals:
        logger.info(f"\n{'='*50}")
        logger.info(f"回测 {symbol} {interval}")
        logger.info(f"{'='*50}")
        
        try:
            # 获取K线数据
            logger.info(f"正在获取K线数据...")
            klines = await fetch_klines_from_okx(symbol, interval, days=7)
            
            if not klines or len(klines) < 100:
                logger.warning(f"K线数据不足: {len(klines) if klines else 0}")
                continue
            
            logger.info(f"获取到 {len(klines)} 根K线")
            logger.info(f"时间范围: {datetime.fromtimestamp(klines[0]['timestamp']/1000)} ~ {datetime.fromtimestamp(klines[-1]['timestamp']/1000)}")
            
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
            results[interval] = stats
            
            logger.info(f"总收益率: {stats['total_return_pct']:.2f}%")
            logger.info(f"最大回撤: {stats['max_drawdown_pct']:.2f}%")
            logger.info(f"胜率: {stats['win_rate']:.1f}%")
            logger.info(f"交易次数: {stats['total_trades']}")
            logger.info(f"盈亏比: {stats['profit_factor']:.2f}")
            logger.info(f"做多次数: {stats.get('long_trades', 0)}")
            logger.info(f"做空次数: {stats.get('short_trades', 0)}")
            
        except Exception as e:
            logger.error(f"回测失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 对比结果
    print("\n" + "="*80)
    print("📊 双向持仓策略回测对比结果")
    print("="*80)
    print(f"{'周期':<8} {'收益率':<12} {'最大回撤':<12} {'胜率':<10} {'交易次数':<10} {'盈亏比':<10} {'做多':<8} {'做空':<8}")
    print("-"*80)
    
    best_interval = None
    best_return = -float('inf')
    
    for interval in intervals:
        if interval in results:
            r = results[interval]
            print(f"{interval:<8} {r['total_return_pct']:>10.2f}% {r['max_drawdown_pct']:>10.2f}% {r['win_rate']:>8.1f}% {r['total_trades']:>10} {r['profit_factor']:>10.2f} {r.get('long_trades', 0):>8} {r.get('short_trades', 0):>8}")
            
            if r['total_return_pct'] > best_return:
                best_return = r['total_return_pct']
                best_interval = interval
    
    print("="*80)
    if best_interval:
        print(f"✅ 推荐周期: {best_interval} (收益率: {best_return:.2f}%)")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_backtest_comparison())
