"""
初始化回测系统数据库表

使用方法:
    python init_backtest_db.py
"""
from app.core.database import engine, Base
from app.models import Kline, Backtest, BacktestTrade
from loguru import logger


def init_backtest_tables():
    """初始化回测系统相关表"""
    try:
        logger.info("开始创建回测系统数据表...")

        # 创建所有表
        Base.metadata.create_all(bind=engine)

        logger.info("✅ 数据表创建成功!")
        logger.info(f"   - klines (K线数据表)")
        logger.info(f"   - backtests (回测记录表)")
        logger.info(f"   - backtest_trades (回测交易表)")

        return True

    except Exception as e:
        logger.error(f"❌ 创建数据表失败: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("回测系统数据库初始化")
    logger.info("=" * 60)

    success = init_backtest_tables()

    if success:
        logger.info("=" * 60)
        logger.info("✅ 初始化完成!")
        logger.info("=" * 60)
    else:
        logger.error("=" * 60)
        logger.error("❌ 初始化失败!")
        logger.error("=" * 60)
