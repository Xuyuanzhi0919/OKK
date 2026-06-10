"""
AI市场分析API端点
提供多因子分析、决策建议等功能
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
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


class TopAltcoinStrategyRequest(BaseModel):
    limit: int = 5
    inst_type: str = "SWAP"
    quote_ccy: str = "USDT"
    min_volume_usdt: float = 1000000
    exclude_majors: bool = True


MAJOR_AND_STABLE_COINS = {
    "BTC", "ETH", "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDD", "USD",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _base_ccy_from_inst_id(inst_id: str) -> str:
    return inst_id.split("-")[0].upper() if inst_id else ""


def _ticker_change_pct(ticker: Dict[str, Any]) -> float:
    last = _to_float(ticker.get("last"))
    open24h = _to_float(ticker.get("open24h"))
    if last <= 0 or open24h <= 0:
        return 0.0
    return (last - open24h) / open24h * 100


def _ticker_volume_usdt(ticker: Dict[str, Any]) -> float:
    volume_ccy = _to_float(ticker.get("volCcy24h"))
    last = _to_float(ticker.get("last"))
    return max(
        volume_ccy,
        volume_ccy * last,
        _to_float(ticker.get("vol24h")) * last,
    )


def _strategy_from_analysis(analysis: Dict[str, Any], change_pct: float, volume_usdt: float) -> Dict[str, Any]:
    decision = analysis.get("decision") or "wait"
    risk_level = analysis.get("risk_level") or "high"
    confidence = _to_float(analysis.get("confidence"))

    if decision == "long":
        direction = "long"
    elif decision == "short":
        direction = "short"
    else:
        direction = "both"

    if risk_level == "low" and confidence >= 0.7:
        risk_per_trade = 0.02
        max_position_usd = 2000
        leverage = 3
    elif risk_level == "medium":
        risk_per_trade = 0.015
        max_position_usd = 1500
        leverage = 3
    else:
        risk_per_trade = 0.01
        max_position_usd = 1000
        leverage = 2

    if volume_usdt < 5000000:
        max_position_usd = min(max_position_usd, 500)
        leverage = min(leverage, 2)

    return {
        "type": "adaptive_grid_trend",
        "label": "自适应趋势网格",
        "direction": direction,
        "timeframe": "15m",
        "parameters": {
            "direction": direction,
            "trend_timeframe": "15m",
            "fast_period": 30,
            "slow_period": 120,
            "atr_period": 14,
            "entry_atr_multiple": 0.2,
            "stop_atr_multiple": 1.6,
            "take_profit_atr_multiple": 3.0,
            "risk_per_trade": risk_per_trade,
            "max_position_usd": max_position_usd,
            "leverage": leverage,
            "margin_mode": "isolated",
            "cooldown_seconds": 1800,
            "notify_near_trigger": True,
            "near_trigger_pct": 0.003,
            "near_trigger_cooldown_seconds": 600,
            "risk_fuse": {
                "enabled": True,
                "max_consecutive_losses": 3,
                "daily_loss_limit_pct": 0.02,
                "max_drawdown_pct": 0.05,
                "profit_factor_window": 10,
                "min_trades_for_profit_factor": 8,
                "min_profit_factor": 0.8,
                "cancel_orders_on_trigger": True,
                "close_position_on_trigger": False,
            },
        },
    }


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
            simulated=api_config.is_simulated
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


@router.post("/top-altcoin-strategies")
async def analyze_top_altcoin_strategies(
    request: TopAltcoinStrategyRequest,
    user_id: int = Depends(get_current_user_api_config),
    db: Session = Depends(get_db)
):
    """
    选择24h涨幅榜前N个USDT山寨币并给出策略建议。
    """
    api_config = db.query(APIConfig).filter(
        APIConfig.user_id == user_id,
        APIConfig.is_active == True
    ).first()

    if not api_config:
        raise HTTPException(status_code=400, detail="请先配置OKX API密钥")

    from app.models.ai_config import AIConfig
    ai_config = db.query(AIConfig).filter(
        AIConfig.user_id == user_id,
        AIConfig.is_active == True
    ).first()

    exchange = OKXExchange(
        api_key=api_config.api_key,
        secret_key=api_config.secret_key,
        passphrase=api_config.passphrase,
        simulated=api_config.is_simulated
    )

    try:
        tickers = await exchange.get_tickers(request.inst_type.upper())
        suffix = f"-{request.quote_ccy.upper()}-SWAP" if request.inst_type.upper() == "SWAP" else f"-{request.quote_ccy.upper()}"

        candidates = []
        for ticker in tickers:
            inst_id = ticker.get("instId", "")
            if not inst_id.endswith(suffix):
                continue

            base_ccy = _base_ccy_from_inst_id(inst_id)
            if request.exclude_majors and base_ccy in MAJOR_AND_STABLE_COINS:
                continue

            change_pct = _ticker_change_pct(ticker)
            volume_usdt = _ticker_volume_usdt(ticker)
            if change_pct <= 0 or volume_usdt < request.min_volume_usdt:
                continue

            candidates.append({
                "symbol": inst_id,
                "base_ccy": base_ccy,
                "last": _to_float(ticker.get("last")),
                "open24h": _to_float(ticker.get("open24h")),
                "high24h": _to_float(ticker.get("high24h")),
                "low24h": _to_float(ticker.get("low24h")),
                "volume_usdt": volume_usdt,
                "change_pct": change_pct,
            })

        top_candidates = sorted(candidates, key=lambda item: item["change_pct"], reverse=True)[:request.limit]
        analyzer = MultiFactorAnalyzer(exchange, ai_config.api_key if ai_config else None)

        results: List[Dict[str, Any]] = []
        for candidate in top_candidates:
            try:
                analysis = await analyzer.analyze(candidate["symbol"])
            except Exception as exc:
                logger.error(f"涨幅榜分析失败 {candidate['symbol']}: {exc}")
                analysis = analyzer._get_default_analysis(candidate["symbol"])

            recommendation = _strategy_from_analysis(
                analysis,
                candidate["change_pct"],
                candidate["volume_usdt"],
            )
            results.append({
                **candidate,
                "change_pct": round(candidate["change_pct"], 2),
                "volume_usdt": round(candidate["volume_usdt"], 2),
                "analysis": analysis,
                "recommended_strategy": recommendation,
            })

        return {
            "code": 0,
            "msg": "success",
            "data": {
                "items": results,
                "universe_count": len(candidates),
                "ai_enabled": ai_config is not None,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"涨幅榜山寨币策略分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"涨幅榜分析失败: {str(e)}")
    finally:
        await exchange.close()
