"""
清空 API 配置数据
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.api_config import APIConfig
from loguru import logger


def clear_api_configs():
    """删除所有 API 配置"""
    db = SessionLocal()

    try:
        # 查询所有配置
        configs = db.query(APIConfig).all()
        count = len(configs)

        if count == 0:
            logger.info("没有需要删除的 API 配置")
            return

        # 删除所有配置
        db.query(APIConfig).delete()
        db.commit()

        logger.info(f"成功删除 {count} 个API配置")

    except Exception as e:
        logger.error(f"删除API配置失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    clear_api_configs()
    logger.info("API配置数据已清空")
