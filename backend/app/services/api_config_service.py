"""
API配置服务 - 动态获取当前激活的API配置
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.api_config import APIConfig
from app.services.exchange.okx import OKXExchange
from app.core.config import settings
from loguru import logger


class APIConfigService:
    """API配置服务"""

    @staticmethod
    def get_active_config(user_id: int = 1, db: Optional[Session] = None) -> Optional[APIConfig]:
        """
        获取用户当前激活的API配置

        Args:
            user_id: 用户ID
            db: 数据库会话,如果为None则创建新会话

        Returns:
            APIConfig对象或None
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            config = db.query(APIConfig).filter(
                APIConfig.user_id == user_id,
                APIConfig.is_active == True
            ).first()

            return config
        finally:
            if should_close:
                db.close()

    @staticmethod
    def get_exchange(user_id: int = 1) -> OKXExchange:
        """
        获取OKX交易所实例 (优先使用数据库配置,否则使用.env配置)

        Args:
            user_id: 用户ID

        Returns:
            OKXExchange实例
        """
        # 尝试从数据库获取激活配置
        config = APIConfigService.get_active_config(user_id)

        if config and config.is_valid:
            logger.info(f"使用数据库API配置: {config.name} ({'模拟盘' if config.is_simulated else '实盘'})")
            return OKXExchange(
                api_key=config.api_key,
                secret_key=config.secret_key,
                passphrase=config.passphrase,
                simulated=config.is_simulated,
                proxy=config.proxy
            )
        else:
            # 回退到.env配置
            logger.info("使用.env文件API配置")
            if not settings.OKX_API_KEY or not settings.OKX_SECRET_KEY or not settings.OKX_PASSPHRASE:
                raise Exception("未找到有效的API配置,请在数据库或.env文件中配置")

            return OKXExchange(
                api_key=settings.OKX_API_KEY,
                secret_key=settings.OKX_SECRET_KEY,
                passphrase=settings.OKX_PASSPHRASE,
                simulated=settings.OKX_SIMULATED,
                proxy=settings.OKX_PROXY
            )


# 全局实例
api_config_service = APIConfigService()
