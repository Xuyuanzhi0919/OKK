"""
添加 ai_swing_long 策略类型到数据库
"""
import sys
sys.path.insert(0, 'F:\\Cluade Code Project\\OKK\\backend')

from sqlalchemy import create_engine, text
from loguru import logger
from app.core.config import settings


def migrate():
    """添加 ai_swing_long 到 strategy_type 枚举"""

    logger.info("开始数据库迁移: 添加 ai_swing_long 策略类型")

    # 创建同步引擎
    sync_engine = create_engine(
        settings.DATABASE_URL.replace('postgresql+psycopg', 'postgresql+psycopg2')
    )

    with sync_engine.begin() as conn:
        try:
            # 方法1: 尝试直接添加 (PostgreSQL 9.1+)
            logger.info("尝试添加 ai_swing_long 到枚举类型...")
            conn.execute(text(
                "ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'ai_swing_long'"
            ))
            logger.success("✅ 成功添加 ai_swing_long 到 strategy_type 枚举")

        except Exception as e:
            logger.warning(f"方法1失败: {e}")
            logger.info("尝试使用方法2...")

            # 方法2: 重建枚举类型
            try:
                # 创建新的枚举类型
                conn.execute(text("""
                    CREATE TYPE strategy_type_new AS ENUM (
                        'grid',
                        'swing_long',
                        'ai_swing_long',
                        'martin',
                        'trend',
                        'arbitrage',
                        'custom'
                    )
                """))
                logger.info("创建新枚举类型 strategy_type_new")

                # 修改列类型
                conn.execute(text("""
                    ALTER TABLE strategies
                        ALTER COLUMN type TYPE strategy_type_new
                        USING type::text::strategy_type_new
                """))
                logger.info("更新 strategies 表列类型")

                # 删除旧类型
                conn.execute(text("DROP TYPE strategy_type"))
                logger.info("删除旧枚举类型")

                # 重命名新类型
                conn.execute(text("ALTER TYPE strategy_type_new RENAME TO strategy_type"))
                logger.info("重命名新枚举类型")

                logger.success("✅ 成功使用方法2添加 ai_swing_long")

            except Exception as e2:
                logger.error(f"方法2也失败: {e2}")
                raise

    # 验证
    with sync_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'strategy_type'
            ORDER BY e.enumsortorder
        """))

        types = [row[0] for row in result]
        logger.info(f"当前 strategy_type 枚举值: {types}")

        if 'ai_swing_long' in types:
            logger.success("✅ 验证成功: ai_swing_long 已存在于枚举中")
        else:
            logger.error("❌ 验证失败: ai_swing_long 不在枚举中")


if __name__ == "__main__":
    migrate()
    logger.success("🎉 数据库迁移完成!")
