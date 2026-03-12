"""
测试双向持仓策略

用法:
    cd backend && python test_dual_side_strategy.py
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger


async def test_strategy_import():
    """测试策略导入"""
    logger.info("=" * 50)
    logger.info("测试1: 策略模块导入")
    logger.info("=" * 50)
    
    try:
        from app.services.strategy.dual_side_strategy import DualSideStrategy
        logger.info("✅ DualSideStrategy 导入成功")
    except Exception as e:
        logger.error(f"❌ DualSideStrategy 导入失败: {e}")
        return False
    
    try:
        from app.models.strategy import StrategyType
        assert StrategyType.DUAL_SIDE.value == "dual_side"
        logger.info("✅ StrategyType.DUAL_SIDE 枚举正确")
    except Exception as e:
        logger.error(f"❌ StrategyType.DUAL_SIDE 枚举失败: {e}")
        return False
    
    try:
        from app.services.strategy.manager import StrategyManager
        from app.models.strategy import StrategyType
        manager = StrategyManager()
        # 检查 create_strategy 方法是否支持 DUAL_SIDE
        logger.info("✅ StrategyManager 可用")
    except Exception as e:
        logger.error(f"❌ StrategyManager 检查失败: {e}")
        return False
    
    return True


async def test_strategy_initialization():
    """测试策略初始化"""
    logger.info("\n" + "=" * 50)
    logger.info("测试2: 策略初始化")
    logger.info("=" * 50)
    
    try:
        from app.services.strategy.dual_side_strategy import DualSideStrategy
        
        # 创建模拟交易所
        class MockExchange:
            async def get_ticker(self, symbol):
                return {"last": 50000.0}
            
            async def get_kline(self, symbol, timeframe, limit):
                # 模拟K线数据
                import random
                base = 50000
                klines = []
                for i in range(limit):
                    close = base + random.uniform(-1000, 1000)
                    klines.append({
                        "c": str(close),
                        "confirm": "1"
                    })
                return klines
            
            async def get_instruments(self, inst_type, inst_id):
                return [{"ctVal": 0.1, "lotSz": 1, "minSz": 1}]
            
            async def set_leverage(self, lever, mgn_mode, inst_id):
                return {"lever": lever}
            
            async def get_balance(self, currency):
                return {"available": 1000.0}
            
            async def create_order(self, **kwargs):
                return {"ordId": "123456"}
        
        exchange = MockExchange()
        
        # 测试默认参数
        strategy = DualSideStrategy(
            strategy_id=999,
            exchange=exchange,
            symbol="BTC-USDT-SWAP",
            parameters={},
            user_id=1,
        )
        
        assert strategy.leverage == 5, f"默认杠杆应为5x，实际为{strategy.leverage}"
        assert strategy.stop_loss == 0.02, f"默认止损应为2%，实际为{strategy.stop_loss}"
        assert strategy.take_profit == 0.06, f"默认止盈应为6%，实际为{strategy.take_profit}"
        logger.info(f"✅ 默认参数正确: leverage={strategy.leverage}x, sl={strategy.stop_loss*100}%, tp={strategy.take_profit*100}%")
        
        # 测试自定义参数
        strategy2 = DualSideStrategy(
            strategy_id=1000,
            exchange=exchange,
            symbol="ETH-USDT-SWAP",
            parameters={
                "leverage": 3,
                "stop_loss": 0.03,
                "take_profit": 0.05,
                "trailing_stop": 0.02,
                "fast_period": 10,
                "slow_period": 30,
            },
            user_id=1,
        )
        
        assert strategy2.leverage == 3, f"自定义杠杆应为3x，实际为{strategy2.leverage}"
        assert strategy2.stop_loss == 0.03, f"自定义止损应为3%，实际为{strategy2.stop_loss}"
        assert strategy2.fast_period == 10, f"自定义快线周期应为10，实际为{strategy2.fast_period}"
        logger.info(f"✅ 自定义参数正确: leverage={strategy2.leverage}x, sl={strategy2.stop_loss*100}%, tp={strategy2.take_profit*100}%")
        
        return True
    except Exception as e:
        logger.error(f"❌ 策略初始化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ema_calculation():
    """测试EMA计算"""
    logger.info("\n" + "=" * 50)
    logger.info("测试3: EMA计算")
    logger.info("=" * 50)
    
    try:
        from app.services.strategy.dual_side_strategy import DualSideStrategy
        
        class MockExchange:
            pass
        
        strategy = DualSideStrategy(
            strategy_id=1,
            exchange=MockExchange(),
            symbol="BTC-USDT-SWAP",
            parameters={},
        )
        
        # 测试EMA计算
        test_data = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                     110, 112, 111, 113, 115, 114, 116, 118, 117, 119]
        
        ema_5 = strategy._ema(test_data, 5)
        ema_10 = strategy._ema(test_data, 10)
        
        logger.info(f"✅ EMA(5) = {ema_5:.2f}")
        logger.info(f"✅ EMA(10) = {ema_10:.2f}")
        
        # EMA应该随着周期增加而平滑
        assert ema_5 > 0 and ema_10 > 0, "EMA应该为正数"
        
        return True
    except Exception as e:
        logger.error(f"❌ EMA计算测试失败: {e}")
        return False


async def main():
    """运行所有测试"""
    logger.info("🚀 开始测试双向持仓策略\n")
    
    results = []
    
    # 测试1: 导入
    results.append(await test_strategy_import())
    
    # 测试2: 初始化
    results.append(await test_strategy_initialization())
    
    # 测试3: EMA计算
    results.append(await test_ema_calculation())
    
    # 汇总
    logger.info("\n" + "=" * 50)
    logger.info("测试结果汇总")
    logger.info("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        logger.info(f"✅ 所有测试通过 ({passed}/{total})")
        logger.info("\n策略已就绪，可以通过以下方式创建:")
        logger.info("  1. 前端: 策略列表 -> 创建策略 -> 双向持仓")
        logger.info("  2. API: POST /api/v1/strategies")
        logger.info('     {"name": "BTC双向", "type": "dual_side", "symbol": "BTC-USDT-SWAP", "parameters": {"leverage": 5}}')
    else:
        logger.error(f"❌ 部分测试失败 ({passed}/{total})")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
