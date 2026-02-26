#!/usr/bin/env python3
"""
清除数据库中所有策略记录的脚本
"""
import sys
import os

# 添加项目根目录到 Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models.strategy import Strategy
from app.models.order import Order
from loguru import logger


def clear_all_strategies():
    """删除数据库中所有策略记录"""
    db = SessionLocal()
    try:
        # 先统计现有策略数量
        strategy_count = db.query(Strategy).count()
        order_count = db.query(Order).count()
        
        logger.info(f"当前数据库中有 {strategy_count} 个策略, {order_count} 个订单记录")
        
        if strategy_count == 0:
            logger.info("没有策略记录需要删除")
            return
        
        # 确认删除
        confirm = input(f"确认删除所有 {strategy_count} 个策略记录? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("操作已取消")
            return
        
        # 删除所有订单记录（因为有外键关联）
        deleted_orders = db.query(Order).delete()
        logger.info(f"已删除 {deleted_orders} 个订单记录")
        
        # 删除所有策略记录
        deleted_strategies = db.query(Strategy).delete()
        db.commit()
        
        logger.success(f"成功删除 {deleted_strategies} 个策略记录")
        
    except Exception as e:
        db.rollback()
        logger.error(f"删除策略记录失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    clear_all_strategies()
