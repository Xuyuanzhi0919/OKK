"""
OKK量化交易系统 - 回测示例脚本

这个脚本演示如何使用回测系统的完整流程：
1. 下载历史K线数据
2. 运行网格策略回测
3. 获取并分析回测结果
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# API基础URL
BASE_URL = "http://localhost:8000/api/v1/backtest"


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def get_timestamp_range(days: int = 30) -> tuple:
    """
    获取时间戳范围

    Args:
        days: 往前推几天

    Returns:
        (start_time, end_time) 毫秒时间戳
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)

    return start_ts, end_ts


def fetch_kline_data(symbol: str = "BTC-USDT", interval: str = "1H", days: int = 30) -> bool:
    """
    步骤1: 下载历史K线数据

    Args:
        symbol: 交易对
        interval: K线周期 (1m, 5m, 15m, 30m, 1H, 4H, 1D)
        days: 下载最近多少天的数据

    Returns:
        是否成功
    """
    print_section("步骤1: 下载历史K线数据")

    start_time, end_time = get_timestamp_range(days)

    print(f"交易对: {symbol}")
    print(f"周期: {interval}")
    print(f"时间范围: {datetime.fromtimestamp(start_time/1000)} ~ {datetime.fromtimestamp(end_time/1000)}")
    print(f"数据天数: {days}天\n")

    payload = {
        "symbol": symbol,
        "interval": interval,
        "start_time": start_time,
        "end_time": end_time
    }

    print("正在从OKX获取K线数据...")

    try:
        response = requests.post(
            f"{BASE_URL}/fetch-kline",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        print(f"成功! 已保存 {result.get('saved_count', 0)} 条K线数据")
        print(f"数据范围: {result.get('start_time', 'N/A')} ~ {result.get('end_time', 'N/A')}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"失败: {e}")
        return False


def run_grid_backtest(
    symbol: str = "BTC-USDT",
    interval: str = "1H",
    days: int = 30,
    initial_capital: float = 10000,
    grid_num: int = 20,
    price_lower: float = 60000,
    price_upper: float = 70000,
    amount_per_grid: float = 500
) -> Dict[str, Any]:
    """
    步骤2: 运行网格策略回测

    Args:
        symbol: 交易对
        interval: K线周期
        days: 回测天数
        initial_capital: 初始资金
        grid_num: 网格数量
        price_lower: 价格下限
        price_upper: 价格上限
        amount_per_grid: 每格投入金额

    Returns:
        回测结果
    """
    print_section("步骤2: 运行网格策略回测")

    start_time, end_time = get_timestamp_range(days)

    print(f"回测参数:")
    print(f"  交易对: {symbol}")
    print(f"  周期: {interval}")
    print(f"  初始资金: ${initial_capital:,.2f}")
    print(f"  网格数量: {grid_num}")
    print(f"  价格区间: ${price_lower:,.2f} ~ ${price_upper:,.2f}")
    print(f"  每格金额: ${amount_per_grid:,.2f}\n")

    payload = {
        "symbol": symbol,
        "interval": interval,
        "start_time": start_time,
        "end_time": end_time,
        "initial_capital": initial_capital,
        "params": {
            "grid_num": grid_num,
            "price_lower": price_lower,
            "price_upper": price_upper,
            "amount_per_grid": amount_per_grid
        }
    }

    print("正在运行回测...")

    try:
        response = requests.post(
            f"{BASE_URL}/run/grid",
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        result = response.json()

        print("回测完成!\n")
        return result

    except requests.exceptions.RequestException as e:
        print(f"失败: {e}")
        return {}


def print_backtest_results(result: Dict[str, Any]):
    """
    步骤3: 打印回测结果

    Args:
        result: 回测结果数据
    """
    print_section("步骤3: 回测结果分析")

    if not result:
        print("无结果数据")
        return

    # 基本信息
    print(f"回测ID: {result.get('id', 'N/A')}")
    print(f"策略类型: {result.get('strategy_type', 'N/A')}")
    print(f"交易对: {result.get('symbol', 'N/A')}")
    print(f"K线周期: {result.get('interval', 'N/A')}\n")

    # 资金变化
    initial = result.get('initial_capital', 0)
    final = result.get('final_capital', 0)
    profit = final - initial

    print(f"资金变化:")
    print(f"  初始资金: ${initial:,.2f}")
    print(f"  最终资金: ${final:,.2f}")
    print(f"  绝对盈亏: ${profit:,.2f} ({'盈利' if profit >= 0 else '亏损'})\n")

    # 性能指标
    print(f"性能指标:")
    print(f"  总收益率: {result.get('total_return', 0) * 100:.2f}%")
    print(f"  年化收益率: {result.get('annual_return', 0) * 100:.2f}%")
    print(f"  夏普比率: {result.get('sharpe_ratio', 0):.2f} {'(优秀)' if result.get('sharpe_ratio', 0) > 2.0 else '(良好)' if result.get('sharpe_ratio', 0) > 1.0 else '(一般)'}")
    print(f"  最大回撤: {result.get('max_drawdown', 0) * 100:.2f}%")
    print(f"  胜率: {result.get('win_rate', 0) * 100:.1f}%\n")

    # 交易统计
    print(f"交易统计:")
    print(f"  总交易次数: {result.get('total_trades', 0)}")
    print(f"  盈利交易: {int(result.get('total_trades', 0) * result.get('win_rate', 0))}")
    print(f"  亏损交易: {result.get('total_trades', 0) - int(result.get('total_trades', 0) * result.get('win_rate', 0))}\n")

    # 策略参数
    params = result.get('strategy_params', {})
    if params:
        print(f"策略参数:")
        for key, value in params.items():
            print(f"  {key}: {value}")
        print()

    # 总结建议
    print_section("总结与建议")

    total_return = result.get('total_return', 0)
    sharpe = result.get('sharpe_ratio', 0)
    max_dd = result.get('max_drawdown', 0)
    win_rate = result.get('win_rate', 0)

    if total_return > 0 and sharpe > 1.5 and max_dd < 0.15 and win_rate > 0.6:
        print("评级: 优秀")
        print("建议: 该策略表现优异，可以考虑应用到实盘交易")
        print("注意: 建议先在模拟盘测试，并设置合理的止损")
    elif total_return > 0 and sharpe > 1.0:
        print("评级: 良好")
        print("建议: 策略整体表现不错，但还有优化空间")
        print("优化方向: 尝试调整网格数量和价格区间")
    elif total_return > 0:
        print("评级: 一般")
        print("建议: 策略勉强盈利，需要进一步优化")
        print("优化方向: 测试不同的参数组合，或考虑其他策略")
    else:
        print("评级: 不佳")
        print("建议: 该参数组合在历史数据上表现不佳")
        print("优化方向: 重新评估策略逻辑和参数设置")


def get_backtest_result(backtest_id: int) -> Dict[str, Any]:
    """
    获取回测结果详情

    Args:
        backtest_id: 回测ID

    Returns:
        回测结果
    """
    try:
        response = requests.get(f"{BASE_URL}/results/{backtest_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取回测结果失败: {e}")
        return {}


def list_backtests(limit: int = 10):
    """
    查看回测历史列表

    Args:
        limit: 返回数量
    """
    print_section("回测历史列表")

    try:
        response = requests.get(f"{BASE_URL}/list?limit={limit}")
        response.raise_for_status()
        backtests = response.json()

        if not backtests:
            print("暂无回测记录")
            return

        print(f"最近{len(backtests)}次回测:\n")
        for bt in backtests:
            profit = bt.get('final_capital', 0) - bt.get('initial_capital', 0)
            print(f"ID: {bt.get('id')} | {bt.get('symbol')} | "
                  f"收益: ${profit:,.2f} ({bt.get('total_return', 0)*100:.2f}%) | "
                  f"夏普: {bt.get('sharpe_ratio', 0):.2f} | "
                  f"{bt.get('created_at', 'N/A')}")

    except requests.exceptions.RequestException as e:
        print(f"获取回测列表失败: {e}")


def check_data_range():
    """查看已有的K线数据范围"""
    print_section("查看已有K线数据")

    try:
        response = requests.get(f"{BASE_URL}/data-range")
        response.raise_for_status()
        data_ranges = response.json()

        if not data_ranges:
            print("暂无K线数据")
            return

        print(f"已有数据:\n")
        for item in data_ranges:
            print(f"{item.get('symbol')} - {item.get('interval')}:")
            print(f"  数据量: {item.get('count', 0)} 条")
            print(f"  时间范围: {item.get('start_time', 'N/A')} ~ {item.get('end_time', 'N/A')}\n")

    except requests.exceptions.RequestException as e:
        print(f"获取数据范围失败: {e}")


def main():
    """主函数 - 完整回测流程"""
    print("\n")
    print("*" * 60)
    print("*" + " " * 58 + "*")
    print("*" + "  OKK量化交易系统 - 回测示例脚本".center(56) + "  *")
    print("*" + " " * 58 + "*")
    print("*" * 60)

    # 配置参数
    SYMBOL = "BTC-USDT"
    INTERVAL = "1H"
    DAYS = 30
    INITIAL_CAPITAL = 10000
    GRID_NUM = 20
    PRICE_LOWER = 60000
    PRICE_UPPER = 70000
    AMOUNT_PER_GRID = 500

    # 先查看已有数据
    check_data_range()

    # 步骤1: 下载K线数据
    success = fetch_kline_data(
        symbol=SYMBOL,
        interval=INTERVAL,
        days=DAYS
    )

    if not success:
        print("\n数据下载失败，请检查:")
        print("1. 后端服务是否正常运行 (http://localhost:8000)")
        print("2. OKX API代理配置是否正确")
        print("3. 网络连接是否正常")
        return

    # 等待一下
    time.sleep(2)

    # 步骤2: 运行回测
    result = run_grid_backtest(
        symbol=SYMBOL,
        interval=INTERVAL,
        days=DAYS,
        initial_capital=INITIAL_CAPITAL,
        grid_num=GRID_NUM,
        price_lower=PRICE_LOWER,
        price_upper=PRICE_UPPER,
        amount_per_grid=AMOUNT_PER_GRID
    )

    if not result:
        print("\n回测失败，请检查:")
        print("1. K线数据是否下载成功")
        print("2. 策略参数是否合理")
        print("3. 数据库连接是否正常")
        return

    # 步骤3: 分析结果
    print_backtest_results(result)

    # 查看历史记录
    list_backtests(limit=5)

    print_section("完成")
    print("回测流程执行完毕!")
    print("\n下一步:")
    print("1. 尝试调整策略参数，观察结果变化")
    print("2. 对比不同参数组合的性能指标")
    print("3. 找到最优参数后应用到实盘策略")
    print("\nAPI文档: http://localhost:8000/docs#/Backtest")
    print()


if __name__ == "__main__":
    main()
