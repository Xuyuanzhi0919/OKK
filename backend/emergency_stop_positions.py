"""
紧急平仓脚本 - 手动平掉所有持仓
用于策略未运行但有持仓的情况
"""
import asyncio
from app.services.exchange.okx import OKXExchange
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.strategy import Strategy
from decimal import Decimal
from loguru import logger

async def emergency_close_all():
    """紧急平掉所有持仓"""

    # 初始化交易所
    exchange = OKXExchange(
        api_key=settings.OKX_API_KEY,
        secret_key=settings.OKX_SECRET_KEY,
        passphrase=settings.OKX_PASSPHRASE,
        proxy=settings.OKX_PROXY,
        simulated=True
    )

    try:
        # 获取所有持仓
        positions = await exchange.get_positions(inst_type="SWAP")

        logger.info(f"找到 {len(positions)} 个持仓")

        for pos in positions:
            pos_size = Decimal(str(pos.get('pos', 0)))
            if pos_size == 0:
                continue

            inst_id = pos.get('instId')
            avg_px = Decimal(str(pos.get('avgPx', 0)))
            mark_px = Decimal(str(pos.get('markPx', 0)))
            upl = Decimal(str(pos.get('upl', 0)))
            upl_ratio = Decimal(str(pos.get('uplRatio', 0))) * 100

            logger.info(f"\n持仓: {inst_id}")
            logger.info(f"  数量: {pos_size}张")
            logger.info(f"  开仓价: {avg_px}")
            logger.info(f"  当前价: {mark_px}")
            logger.info(f"  未实现盈亏: {upl} USDT ({upl_ratio:.2f}%)")

            # 判断是否需要平仓
            if abs(upl_ratio) >= 5:  # 盈利或亏损超过5%
                logger.warning(f"  ⚠️ 盈亏已超过5%,建议平仓")

                # 询问是否平仓
                response = input(f"是否平仓 {inst_id}? (yes/no): ")
                if response.lower() == 'yes':
                    # 平仓
                    side = 'sell' if pos_size > 0 else 'buy'
                    logger.info(f"正在平仓: {side} {abs(pos_size)}张...")

                    try:
                        order = await exchange.create_order(
                            symbol=inst_id,
                            side=side,
                            order_type='market',
                            amount=abs(float(pos_size)),
                            td_mode='isolated',
                            pos_side='net',
                            reduce_only=True  # 只减仓
                        )

                        if order and order.get('ordId'):
                            logger.info(f"✅ 平仓订单已提交: {order.get('ordId')}")
                        else:
                            logger.error(f"❌ 平仓失败: {order}")
                    except Exception as e:
                        logger.error(f"❌ 平仓异常: {e}")
                else:
                    logger.info("跳过平仓")
            else:
                logger.info(f"  盈亏在正常范围内")

        await exchange.close()

    except Exception as e:
        logger.error(f"紧急平仓失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("紧急平仓工具")
    logger.info("=" * 60)
    logger.info("此工具将扫描所有持仓并询问是否平仓")
    logger.info("适用于策略未运行但有持仓需要处理的情况")
    logger.info("=" * 60)

    asyncio.run(emergency_close_all())

    logger.info("\n完成")
