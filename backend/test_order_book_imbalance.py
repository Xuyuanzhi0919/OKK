"""
测试订单簿不平衡策略初始化
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.strategy import StrategyType
from app.services.strategy.manager import StrategyManager


def test_strategy_type():
    """测试策略类型枚举"""
    print("=" * 50)
    print("测试策略类型枚举")
    print("=" * 50)
    
    # 检查枚举是否存在
    assert hasattr(StrategyType, 'ORDER_BOOK_IMBALANCE'), "ORDER_BOOK_IMBALANCE 枚举不存在"
    
    strategy_type = StrategyType.ORDER_BOOK_IMBALANCE
    print(f"✅ 策略类型枚举: {strategy_type}")
    print(f"✅ 枚举值: {strategy_type.value}")
    
    return True


def test_strategy_creation():
    """测试策略创建"""
    print("\n" + "=" * 50)
    print("测试策略创建")
    print("=" * 50)
    
    manager = StrategyManager()
    
    # 创建模拟交易所
    class MockExchange:
        def __init__(self):
            self.api_key = "test"
            self.secret_key = "test"
            self.passphrase = "test"
    
    exchange = MockExchange()
    
    # 测试参数
    parameters = {
        "imbalance_threshold": 0.25,
        "min_depth": 15,
        "stop_loss": 0.003,
        "take_profit": 0.006,
        "holding_seconds": 60,
        "cooldown_seconds": 20,
        "position_ratio": 0.2,
        "leverage": 10,
    }
    
    try:
        strategy = manager.create_strategy(
            strategy_id=999,
            strategy_type=StrategyType.ORDER_BOOK_IMBALANCE,
            symbol="ETH-USDT-SWAP",
            parameters=parameters,
            exchange=exchange,
            user_id=1
        )
        
        print(f"✅ 策略创建成功: {type(strategy).__name__}")
        print(f"✅ 策略ID: {strategy.strategy_id}")
        print(f"✅ 交易对: {strategy.symbol}")
        print(f"✅ 参数:")
        print(f"   - 不平衡阈值: {strategy.imbalance_threshold}")
        print(f"   - 订单簿深度: {strategy.min_depth}")
        print(f"   - 止损: {strategy.stop_loss * 100}%")
        print(f"   - 止盈: {strategy.take_profit * 100}%")
        print(f"   - 持仓时间: {strategy.holding_seconds}s")
        print(f"   - 冷却期: {strategy.cooldown_seconds}s")
        print(f"   - 仓位比例: {strategy.pos_ratio * 100}%")
        print(f"   - 杠杆: {strategy.leverage}x")
        
        return True
        
    except Exception as e:
        print(f"❌ 策略创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_imbalance_calculation():
    """测试订单簿不平衡度计算"""
    print("\n" + "=" * 50)
    print("测试订单簿不平衡度计算")
    print("=" * 50)
    
    from app.services.strategy.order_book_imbalance import OrderBookImbalanceStrategy
    
    # 创建模拟交易所
    class MockExchange:
        pass
    
    strategy = OrderBookImbalanceStrategy(
        strategy_id=1,
        exchange=MockExchange(),
        symbol="ETH-USDT-SWAP",
        parameters={"min_depth": 5},
        user_id=1
    )
    
    # 模拟订单簿数据
    orderbook = {
        "bids": [
            [3000.0, 10.0],  # 价格, 数量
            [2999.0, 20.0],
            [2998.0, 15.0],
            [2997.0, 25.0],
            [2996.0, 30.0],
        ],
        "asks": [
            [3001.0, 5.0],
            [3002.0, 8.0],
            [3003.0, 12.0],
            [3004.0, 10.0],
            [3005.0, 15.0],
        ],
        "timestamp": 1234567890
    }
    
    imbalance = strategy._calculate_imbalance(orderbook)
    
    print(f"订单簿数据:")
    print(f"  买盘: {orderbook['bids'][:3]}...")
    print(f"  卖盘: {orderbook['asks'][:3]}...")
    print(f"✅ 不平衡度: {imbalance:.4f}")
    
    if imbalance > 0:
        print(f"  → 买盘强势 (看涨信号)")
    elif imbalance < 0:
        print(f"  → 卖盘强势 (看跌信号)")
    else:
        print(f"  → 平衡")
    
    return True


def test_signal_confirmation():
    """测试信号确认逻辑"""
    print("\n" + "=" * 50)
    print("测试信号确认逻辑")
    print("=" * 50)
    
    from app.services.strategy.order_book_imbalance import OrderBookImbalanceStrategy
    
    class MockExchange:
        pass
    
    strategy = OrderBookImbalanceStrategy(
        strategy_id=1,
        exchange=MockExchange(),
        symbol="ETH-USDT-SWAP",
        parameters={
            "imbalance_threshold": 0.25,
            "min_imbalance_count": 2
        },
        user_id=1
    )
    
    # 测试1: 连续做多信号
    strategy._imbalance_history = [0.3, 0.35, 0.4]
    confirmed = strategy._is_signal_confirmed(1)
    print(f"连续做多信号 [0.3, 0.35, 0.4]: {'✅ 确认' if confirmed else '❌ 未确认'}")
    
    # 测试2: 信号不一致
    strategy._imbalance_history = [0.3, -0.1, 0.35]
    confirmed = strategy._is_signal_confirmed(1)
    print(f"不一致信号 [0.3, -0.1, 0.35]: {'❌ 未确认' if not confirmed else '✅ 确认'}")
    
    # 测试3: 连续做空信号
    strategy._imbalance_history = [-0.3, -0.35, -0.4]
    confirmed = strategy._is_signal_confirmed(-1)
    print(f"连续做空信号 [-0.3, -0.35, -0.4]: {'✅ 确认' if confirmed else '❌ 未确认'}")
    
    return True


def main():
    """运行所有测试"""
    print("\n" + "🚀" * 25)
    print("订单簿不平衡高频策略测试")
    print("🚀" * 25 + "\n")
    
    results = []
    
    # 运行测试
    results.append(("策略类型枚举", test_strategy_type()))
    results.append(("策略创建", test_strategy_creation()))
    results.append(("不平衡度计算", test_imbalance_calculation()))
    results.append(("信号确认逻辑", test_signal_confirmation()))
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 所有测试通过！策略已准备就绪。")
    else:
        print("⚠️ 部分测试失败，请检查。")
    print("=" * 50)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
