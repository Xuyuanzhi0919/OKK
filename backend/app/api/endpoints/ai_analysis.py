"""
AI市场分析API端点
提供多因子分析、决策建议等功能
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.api.deps import require_current_user_id
from app.services.exchange.okx import OKXExchange
from app.services.ai.multi_factor_analyzer import MultiFactorAnalyzer
from app.models.api_config import APIConfig
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


get_current_user_api_config = require_current_user_id


class AnalysisRequest(BaseModel):
    symbol: str
    detailed: bool = False  # 是否返回详细分析


class AnalysisResponse(BaseModel):
    symbol: str
    timestamp: str
    decision: str  # long | short | wait
    confidence: float
    scores: dict
    factors: dict
    risk_level: str
    suggested_strategy: Optional[str]
    reasoning: str


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_market(
    request: AnalysisRequest,
    user_id: int = Depends(get_current_user_api_config),
    db: Session = Depends(get_db)
):
    """
    AI市场分析接口

    多因子综合分析:
    - 技术指标 (40%)
    - 市场情绪 (30%)
    - AI深度分析 (30%)
    """
    try:
        # 获取用户的API配置
        api_config = db.query(APIConfig).filter(
            APIConfig.user_id == user_id,
            APIConfig.is_active == True
        ).first()

        if not api_config:
            raise HTTPException(status_code=400, detail="请先配置OKX API密钥")

        # 获取用户的AI配置
        from app.models.ai_config import AIConfig
        ai_config = db.query(AIConfig).filter(
            AIConfig.user_id == user_id,
            AIConfig.is_active == True
        ).first()

        if not ai_config:
            raise HTTPException(status_code=400, detail="请先配置AI服务")

        # 创建交易所实例
        exchange = OKXExchange(
            api_key=api_config.api_key,
            secret_key=api_config.secret_key,
            passphrase=api_config.passphrase,
            simulated=api_config.is_simulated
        )

        # 创建分析器
        analyzer = MultiFactorAnalyzer(exchange, ai_config.api_key)

        # 执行分析
        result = await analyzer.analyze(request.symbol)

        logger.info(f"分析完成: {request.symbol} -> {result['decision']} (信心度: {result['confidence']})")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"市场分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/analysis/{symbol}")
async def get_analysis(
    symbol: str,
    user_id: int = Depends(get_current_user_api_config),
    db: Session = Depends(get_db)
):
    """
    GET方式调用分析（简化版）
    """
    return await analyze_market(
        AnalysisRequest(symbol=symbol, detailed=False),
        user_id,
        db
    )


@router.post("/analyze/batch")
async def analyze_batch(
    symbols: list[str],
    user_id: int = Depends(get_current_user_api_config),
    db: Session = Depends(get_db)
):
    """
    批量分析多个交易对

    返回每个交易对的分析结果
    """
    try:
        # 获取用户的API配置
        api_config = db.query(APIConfig).filter(
            APIConfig.user_id == user_id,
            APIConfig.is_active == True
        ).first()

        if not api_config:
            raise HTTPException(status_code=400, detail="请先配置API密钥")

        exchange = OKXExchange(
            api_key=api_config.api_key,
            secret_key=api_config.secret_key,
            passphrase=api_config.passphrase,
            is_simulated=api_config.is_simulated
        )

        analyzer = MultiFactorAnalyzer(exchange)

        results = []
        for symbol in symbols:
            try:
                result = await analyzer.analyze(symbol)
                results.append(result)
            except Exception as e:
                logger.error(f"分析{symbol}失败: {e}")
                results.append({
                    "symbol": symbol,
                    "error": str(e)
                })

        return {"results": results}

    except Exception as e:
        logger.error(f"批量分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量分析失败: {str(e)}")
