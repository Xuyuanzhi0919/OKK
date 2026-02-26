"""
批量取消待成交订单
"""
import asyncio
from app.services.exchange.okx import OKXExchange
from app.core.config import settings
from loguru import logger

async def cancel_all_pending_orders():
    """取消所有待成交订单"""
    # 初始化交易所
    exchange = OKXExchange(
        api_key=settings.OKX_API_KEY,
        secret_key=settings.OKX_SECRET_KEY,
        passphrase=settings.OKX_PASSPHRASE,
        simulated=settings.OKX_SIMULATED,
        proxy=settings.OKX_PROXY
    )

    try:
        # 获取所有待成交订单
        logger.info("查询所有待成交订单...")
        orders = await exchange.get_orders(
            inst_type="SWAP",
            state="live"  # live表示待成交
        )

        if not orders:
            logger.info("✅ 没有待成交订单")
            return

        logger.info(f"找到 {len(orders)} 笔待成交订单")

        # 取消每笔订单
        for order in orders:
            order_id = order.get("ordId")
            inst_id = order.get("instId")
            side = order.get("side")
            size = order.get("sz")

            logger.info(f"取消订单: {inst_id} {side} {size}张 - 订单ID: {order_id}")

            try:
                result = await exchange.cancel_order(
                    inst_id=inst_id,
                    ord_id=order_id
                )

                if result:
                    logger.success(f"✅ 订单 {order_id} 已取消")
                else:
                    logger.error(f"❌ 取消订单 {order_id} 失败")

            except Exception as e:
                logger.error(f"❌ 取消订单 {order_id} 异常: {e}")

        logger.success("✅ 批量取消完成")

    except Exception as e:
        logger.error(f"查询订单失败: {e}")

if __name__ == "__main__":
    asyncio.run(cancel_all_pending_orders())
