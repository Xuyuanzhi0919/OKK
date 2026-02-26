"""
手动恢复策略28
"""
import asyncio
from app.core.database import SessionLocal
from app.models.strategy import Strategy
from app.services.strategy.manager import strategy_manager
from app.services.api_config_service import api_config_service
from loguru import logger

async def recover_strategy_28():
    """手动恢复策略28"""
    db = SessionLocal()
    try:
        # 查询策略28
        strategy = db.query(Strategy).filter(Strategy.id == 28).first()

        if not strategy:
            logger.error("策略28不存在")
            return

        logger.info(f"找到策略: {strategy.name} ({strategy.symbol})")
        logger.info(f"当前状态: {strategy.status}")

        # 获取API配置
        exchange = api_config_service.get_exchange(user_id=strategy.user_id, db=db)

        if not exchange:
            logger.error("无法获取API配置")
            return

        # 启动策略
        logger.info("正在启动策略...")
        await strategy_manager.start_strategy(
            strategy_id=strategy.id,
            strategy_type=strategy.type,
            symbol=strategy.symbol,
            parameters=strategy.parameters,
            exchange=exchange,
            user_id=strategy.user_id
        )

        logger.info("✅ 策略28已恢复并启动")

        # 等待几秒让策略初始化
        await asyncio.sleep(3)

        # 检查策略实例
        instance = strategy_manager.get_strategy(28)
        if instance:
            logger.info(f"策略实例已创建:")
            logger.info(f"  运行状态: {instance.is_running}")
            logger.info(f"  止盈: {instance.take_profit_pct}%")
            logger.info(f"  止损: {instance.stop_loss_pct}%")

            if hasattr(instance, 'position') and instance.position:
                logger.info(f"  持仓: {instance.position.get('contract_amount')}张 @ {instance.position.get('entry_price')}")
            else:
                logger.warning("  策略没有持仓记录,将在下次on_tick时检测")
        else:
            logger.error("策略实例未创建成功")

    except Exception as e:
        logger.error(f"恢复失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("开始恢复策略28...")
    asyncio.run(recover_strategy_28())
    logger.info("完成")
