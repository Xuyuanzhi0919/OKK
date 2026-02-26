"""
插入初始 API 配置数据
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.api_config import APIConfig
from loguru import logger


def seed_api_configs():
    """插入你的两个 API 配置"""
    db = SessionLocal()

    try:
        user_id = 1  # 默认用户ID

        # 检查是否已存在配置
        existing_configs = db.query(APIConfig).filter(
            APIConfig.user_id == user_id
        ).count()

        if existing_configs > 0:
            logger.info(f"用户 {user_id} 已有 {existing_configs} 个API配置,跳过初始化")
            return

        # 实盘配置 (从 .env 文件读取,请替换为你的实盘 API Key)
        real_config = APIConfig(
            user_id=user_id,
            name="OKX 实盘",
            exchange="OKX",
            api_key="your-real-api-key",  # 替换为你的实盘 API Key
            secret_key="your-real-secret-key",  # 替换为你的实盘 Secret Key
            passphrase="your-real-passphrase",  # 替换为你的实盘 Passphrase
            is_simulated=False,
            is_active=False,  # 默认不激活
            proxy="http://127.0.0.1:7897",
            is_valid=True
        )

        # 模拟盘配置 (当前在 .env 中的配置)
        simulated_config = APIConfig(
            user_id=user_id,
            name="OKX 模拟盘",
            exchange="OKX",
            api_key="de03e4d5-175b-4aa3-ad42-17cf7366bcce",
            secret_key="2C2C7A4A158307164B09106A322D2E34",
            passphrase="155062862Xyz.",
            is_simulated=True,
            is_active=True,  # 默认激活模拟盘
            proxy="http://127.0.0.1:7897",
            is_valid=True
        )

        db.add(real_config)
        db.add(simulated_config)
        db.commit()

        logger.info(f"成功为用户 {user_id} 创建了 2 个API配置")
        logger.info(f"  - 实盘配置 (ID: {real_config.id})")
        logger.info(f"  - 模拟盘配置 (ID: {simulated_config.id}) [当前激活]")

    except Exception as e:
        logger.error(f"插入API配置失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_api_configs()
