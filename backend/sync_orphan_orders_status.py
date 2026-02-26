"""
同步孤儿订单状态脚本
用于从OKX同步strategy_id=None的订单的真实状态
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.order import Order, OrderStatus
from app.services.api_config_service import api_config_service
from datetime import datetime, timezone
from loguru import logger

async def sync_orphan_orders(symbol: str = None):
    """同步孤儿订单状态"""
    db = SessionLocal()

    try:
        # 查找孤儿订单
        query = db.query(Order).filter(
            Order.strategy_id == None,
            Order.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED])
        )

        if symbol:
            query = query.filter(Order.symbol == symbol)

        orphan_orders = query.all()

        if not orphan_orders:
            logger.info("✅ 没有找到需要同步的孤儿订单")
            return

        logger.info(f"找到 {len(orphan_orders)} 个孤儿订单，开始同步状态...")

        # 获取交易所实例
        exchange = api_config_service.get_exchange(user_id=1)

        synced_count = 0
        canceled_count = 0
        filled_count = 0
        failed_count = 0

        for order in orphan_orders:
            try:
                logger.info(f"查询订单状态: {order.order_id} ({order.symbol})")

                # 从OKX查询订单真实状态
                order_detail = await exchange.get_order(
                    symbol=order.symbol,
                    order_id=order.order_id
                )

                okx_status = order_detail.get("state")
                filled_size = float(order_detail.get("accFillSz", 0))
                avg_price = order_detail.get("avgPx")

                logger.info(f"  OKX状态: {okx_status}, 成交量: {filled_size}")

                # 映射状态
                status_mapping = {
                    "live": OrderStatus.PENDING,
                    "partially_filled": OrderStatus.PARTIAL_FILLED,
                    "filled": OrderStatus.FILLED,
                    "canceled": OrderStatus.CANCELED,
                }

                new_status = status_mapping.get(okx_status, OrderStatus.PENDING)

                if new_status != order.status or filled_size != order.filled_amount:
                    old_status = order.status
                    order.status = new_status
                    order.filled_amount = filled_size

                    if okx_status == "filled" and avg_price:
                        order.avg_price = float(avg_price)
                        order.filled_at = datetime.now(timezone.utc)
                        filled_count += 1
                    elif okx_status == "canceled":
                        order.canceled_at = datetime.now(timezone.utc)
                        canceled_count += 1

                    synced_count += 1
                    logger.info(f"  ✓ 更新: {old_status.value} → {new_status.value}")

            except Exception as e:
                failed_count += 1
                logger.error(f"  ✗ 同步失败: {e}")

        db.commit()
        await exchange.close()

        logger.info(f"\n✅ 同步完成:")
        logger.info(f"  总计: {len(orphan_orders)} 个")
        logger.info(f"  已更新: {synced_count} 个")
        logger.info(f"  其中已成交: {filled_count} 个")
        logger.info(f"  其中已撤销: {canceled_count} 个")
        logger.info(f"  失败: {failed_count} 个")

    except Exception as e:
        logger.error(f"❌ 同步过程出错: {e}")
        db.rollback()
    finally:
        db.close()

async def main():
    import argparse
    parser = argparse.ArgumentParser(description='同步孤儿订单状态')
    parser.add_argument('--symbol', type=str, help='只同步指定交易对的订单，如 DOGE-USDT')

    args = parser.parse_args()

    await sync_orphan_orders(symbol=args.symbol)

if __name__ == "__main__":
    asyncio.run(main())
