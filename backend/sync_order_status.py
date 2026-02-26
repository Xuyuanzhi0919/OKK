"""
同步订单状态脚本
用于批量更新数据库中订单状态与OKX实际状态不一致的订单
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.order import Order, OrderStatus
from app.services.api_config_service import api_config_service
from datetime import datetime, timezone
from loguru import logger


async def sync_strategy_orders(strategy_id: int):
    """同步指定策略的所有订单状态"""
    db = SessionLocal()

    try:
        # 获取交易所实例
        exchange = api_config_service.get_exchange(user_id=1)

        # 查询该策略的所有SUBMITTED状态订单
        orders = db.query(Order).filter(
            Order.strategy_id == strategy_id,
            Order.status == OrderStatus.SUBMITTED
        ).all()

        logger.info(f"找到 {len(orders)} 个SUBMITTED状态的订单需要同步")

        updated_count = 0
        for order in orders:
            try:
                # 从OKX查询订单最新状态
                order_detail = await exchange.get_order(
                    symbol=order.symbol,
                    order_id=order.order_id
                )

                okx_status = order_detail.get("state")
                filled_size = float(order_detail.get("accFillSz", 0))
                avg_price = order_detail.get("avgPx")

                # 状态映射
                status_mapping = {
                    "live": OrderStatus.PENDING,
                    "partially_filled": OrderStatus.PARTIAL_FILLED,
                    "filled": OrderStatus.FILLED,
                    "canceled": OrderStatus.CANCELED,
                }

                new_status = status_mapping.get(okx_status, OrderStatus.PENDING)

                # 检查是否需要更新
                if new_status != order.status or filled_size != order.filled_amount:
                    old_status = order.status
                    order.status = new_status
                    order.filled_amount = filled_size

                    if okx_status == "filled" and avg_price:
                        order.avg_price = float(avg_price)
                        order.filled_at = datetime.now(timezone.utc)

                    logger.info(
                        f"更新订单 {order.order_id}: "
                        f"状态 {old_status} -> {new_status}, "
                        f"成交量 {order.filled_amount}/{order.amount}"
                    )
                    updated_count += 1

            except Exception as e:
                logger.error(f"同步订单 {order.order_id} 失败: {e}")

        # 提交所有更新
        db.commit()
        logger.info(f"✅ 成功更新 {updated_count} 个订单状态")

        # 关闭交易所连接
        await exchange.close()

    except Exception as e:
        logger.error(f"同步订单状态失败: {e}")
        db.rollback()
    finally:
        db.close()


async def main():
    """主函数"""
    strategy_id = 54  # OKB网格策略ID
    logger.info(f"开始同步策略 {strategy_id} 的订单状态...")
    await sync_strategy_orders(strategy_id)
    logger.info("同步完成！")


if __name__ == "__main__":
    asyncio.run(main())
