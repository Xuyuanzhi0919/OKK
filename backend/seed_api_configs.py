"""
插入初始 API 配置数据
"""
import os

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.api_config import APIConfig
from loguru import logger


def seed_api_configs():
    """按环境变量插入初始 API 配置，避免把真实密钥写进代码仓库。"""
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

        configs = []
        real_api_key = os.getenv("OKX_REAL_API_KEY")
        real_secret_key = os.getenv("OKX_REAL_SECRET_KEY")
        real_passphrase = os.getenv("OKX_REAL_PASSPHRASE")
        if real_api_key and real_secret_key and real_passphrase:
            configs.append(APIConfig(
                user_id=user_id,
                name="OKX 实盘",
                exchange="OKX",
                api_key=real_api_key,
                secret_key=real_secret_key,
                passphrase=real_passphrase,
                is_simulated=False,
                is_active=False,
                proxy=os.getenv("OKX_PROXY") or None,
                is_valid=True
            ))

        simulated_api_key = os.getenv("OKX_SIM_API_KEY") or os.getenv("OKX_API_KEY")
        simulated_secret_key = os.getenv("OKX_SIM_SECRET_KEY") or os.getenv("OKX_SECRET_KEY")
        simulated_passphrase = os.getenv("OKX_SIM_PASSPHRASE") or os.getenv("OKX_PASSPHRASE")
        if simulated_api_key and simulated_secret_key and simulated_passphrase:
            configs.append(APIConfig(
                user_id=user_id,
                name="OKX 模拟盘",
                exchange="OKX",
                api_key=simulated_api_key,
                secret_key=simulated_secret_key,
                passphrase=simulated_passphrase,
                is_simulated=True,
                is_active=True,
                proxy=os.getenv("OKX_PROXY") or None,
                is_valid=True
            ))

        if not configs:
            logger.warning("未检测到 OKX API 环境变量，跳过 API 配置初始化")
            return

        db.add_all(configs)
        db.commit()

        logger.info(f"成功为用户 {user_id} 创建了 {len(configs)} 个API配置")
        for config in configs:
            logger.info(f"  - {config.name} (ID: {config.id})")

    except Exception as e:
        logger.error(f"插入API配置失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_api_configs()
