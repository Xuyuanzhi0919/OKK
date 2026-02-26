"""
网格策略回测测试脚本

测试网格策略在不同参数下的盈利能力
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from loguru import logger
from app.core.database import SessionLocal
from app.services.backtest.grid_backtest import GridBacktestEngine
from app.services.backtest.metrics import BacktestMetrics
from app.models import Kline
from sqlalchemy import and_


def run_grid_backtest(
    symbol: str = "BTC-USDT",
    interval: str = "1H",
    days: int = 30,
    initial_capital: float = 10000,
    grid_num: int = 10,
    price_range_percent: float = 0.10,  # 价格范围百分比
    use_dynamic_range: bool = True,  # 是否使用动态范围(基于历史波动)
):
    """
    运行网格策略回测
    
    Args:
        symbol: 交易对
        interval: K线周期
        days: 回测天数
        initial_capital: 初始资金
        grid_num: 网格数量
        price_range_percent: 价格范围百分比(相对于起始价格)
        use_dynamic_range: 是否使用动态范围(基于历史高低价)
    """
    print("\n" + "=" * 60)
    print(f"网格策略回测测试")
    print("=" * 60)
    print(f"交易对: {symbol}")
    print(f"K线周期: {interval}")
    print(f"回测天数: {days}")
    print(f"初始资金: {initial_capital} USDT")
    print(f"网格数量: {grid_num}")
    print(f"价格范围: ±{price_range_percent*100}%")
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
            print(f"错误: 没有找到K线数据，请先运行 fetch-kline API 获取数据")
            print(f"查询条件: symbol={symbol}, interval={interval}, start={start_ts}, end={end_ts}")
            return None
        
        print(f"获取到 {len(klines)} 条K线数据")
        
        # 计算网格参数
        first_price = float(klines[0].open)
        
        if use_dynamic_range:
            # 使用历史高低价计算网格范围(留有一定余量)
            highs = [float(k.high) for k in klines]
            lows = [float(k.low) for k in klines]
            price_upper = max(highs) * 1.02  # 最高价上方2%
            price_lower = min(lows) * 0.98   # 最低价下方2%
        else:
            price_lower = first_price * (1 - price_range_percent)
            price_upper = first_price * (1 + price_range_percent)
        
        # 计算每格交易数量 - 使用总资金的一部分，预留资金应对价格波动
        usable_capital = initial_capital * 0.9  # 只使用90%的资金
        amount_per_grid = (usable_capital / grid_num) / ((price_upper + price_lower) / 2)
        
        print(f"起始价格: {first_price:.2f}")
        print(f"历史最高: {max(highs):.2f}")
        print(f"历史最低: {min(lows):.2f}")
        print(f"网格下限: {price_lower:.2f}")
        print(f"网格上限: {price_upper:.2f}")
        print(f"每格数量: {amount_per_grid:.4f}")
        
        # 创建回测引擎
        engine = GridBacktestEngine(
            symbol=symbol,
            initial_capital=initial_capital,
            grid_lower=price_lower,
            grid_upper=price_upper,
            grid_num=grid_num,
            amount_per_grid=amount_per_grid,
            fee_rate=0.001  # 0.1% 手续费
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
        final_capital = engine.capital + engine.position.amount * engine.current_kline['close'] if engine.current_kline else engine.capital
        
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


def test_multiple_configs():
    """测试多种参数配置"""
    print("\n" + "=" * 80)
    print("网格策略多参数配置测试")
    print("=" * 80)
    
    configs = [
        # 保守配置
        {"grid_num": 5, "price_range_percent": 0.05, "days": 30},
        # 标准配置
        {"grid_num": 10, "price_range_percent": 0.10, "days": 30},
        # 激进配置
        {"grid_num": 20, "price_range_percent": 0.15, "days": 30},
        # 长期测试
        {"grid_num": 10, "price_range_percent": 0.10, "days": 90},
    ]
    
    results = []
    
    for i, config in enumerate(configs):
        print(f"\n>>> 测试配置 {i+1}/{len(configs)}")
        metrics = run_grid_backtest(
            symbol="BTC-USDT",
            interval="1H",
            days=config["days"],
            initial_capital=10000,
            grid_num=config["grid_num"],
            price_range_percent=config["price_range_percent"]
        )
        
        if metrics:
            results.append({
                "config": config,
                "metrics": metrics
            })
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    print(f"{'配置':<30} {'收益率':>12} {'最大回撤':>12} {'夏普比率':>10} {'胜率':>10}")
    print("-" * 80)
    
    for r in results:
        config = r["config"]
        m = r["metrics"]
        config_str = f"网格{config['grid_num']}, 范围±{config['price_range_percent']*100}%, {config['days']}天"
        print(f"{config_str:<30} {m['total_return']*100:>11.2f}% {m['max_drawdown']*100:>11.2f}% {m['sharpe_ratio']:>10.2f} {m['win_rate']*100:>9.2f}%")
    
    print("=" * 80)
    
    # 找出最佳配置
    if results:
        best = max(results, key=lambda x: x["metrics"]["sharpe_ratio"])
        print(f"\n最佳配置(按夏普比率): 网格{best['config']['grid_num']}, 范围±{best['config']['price_range_percent']*100}%")
        print(f"收益率: {best['metrics']['total_return']:.2f}%, 夏普比率: {best['metrics']['sharpe_ratio']:.2f}")


if __name__ == "__main__":
    # 单次测试
    run_grid_backtest(
        symbol="BTC-USDT",
        interval="1H",
        days=30,
        initial_capital=10000,
        grid_num=10,
        price_range_percent=0.10
    )
    
    # 多配置测试
    # test_multiple_configs()
