"""
持仓和账户管理API
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.exchange.okx import OKXExchange
from app.services.api_config_service import api_config_service
from loguru import logger

router = APIRouter()


def get_okx_exchange() -> OKXExchange:
    """获取OKX交易所实例 (优先使用数据库配置)"""
    try:
        return api_config_service.get_exchange(user_id=1)
    except Exception as e:
        logger.error(f"获取交易所实例失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"API配置错误: {str(e)}"
        )


@router.get("/balance")
async def get_balance(
    ccy: Optional[str] = Query(None, description="币种,如 BTC,ETH。支持多个,逗号分隔")
):
    """
    获取账户余额

    Args:
        ccy: 币种,支持多个币种查询(不超过20个),逗号分隔。不传则返回所有资产

    Returns:
        账户余额信息
    """
    try:
        exchange = get_okx_exchange()
        balance = await exchange.get_balance(ccy=ccy)
        await exchange.close()

        return {
            "code": 0,
            "msg": "success",
            "data": balance
        }
    except Exception as e:
        logger.error(f"获取余额失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_positions(
    inst_type: Optional[str] = Query(None, description="产品类型: MARGIN/SWAP/FUTURES/OPTION"),
    inst_id: Optional[str] = Query(None, description="产品ID,如 BTC-USDT-SWAP"),
    pos_id: Optional[str] = Query(None, description="持仓ID")
):
    """
    获取持仓列表

    Args:
        inst_type: 产品类型
        inst_id: 产品ID,支持多个(不超过10个),逗号分隔
        pos_id: 持仓ID,支持多个(不超过20个),逗号分隔

    Returns:
        持仓列表
    """
    try:
        exchange = get_okx_exchange()
        positions = await exchange.get_positions(
            inst_type=inst_type,
            inst_id=inst_id,
            pos_id=pos_id
        )
        await exchange.close()

        # 安全转换函数
        def safe_float(value, default=0.0):
            """安全地转换为float,处理空字符串和None"""
            if value is None or value == '' or value == "":
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        # 转换为前端需要的格式(直接返回数组)
        result = []
        for idx, pos in enumerate(positions):
            pos_size = safe_float(pos.get('pos', 0))
            if pos_size == 0:
                continue  # 跳过空持仓

            avg_px = safe_float(pos.get('avgPx', 0))
            mark_px = safe_float(pos.get('markPx', avg_px))
            upl = safe_float(pos.get('upl', 0))
            upl_ratio = safe_float(pos.get('uplRatio', 0))
            margin = safe_float(pos.get('margin', 0))
            liq_px = safe_float(pos.get('liqPx', 0))

            result.append({
                "id": idx + 1,
                "strategy_id": None,
                "strategy_name": None,
                "symbol": pos.get('instId', ''),
                "side": "long" if pos_size > 0 else "short",
                "size": abs(pos_size),
                "avg_price": avg_px,
                "current_price": mark_px,
                "unrealized_pnl": upl,
                "unrealized_pnl_pct": upl_ratio * 100,
                "margin": margin,
                "liquidation_price": liq_px if liq_px > 0 else None,
                "created_at": pos.get('cTime', ''),
                "updated_at": pos.get('uTime', '')
            })

        logger.info(f"获取到 {len(result)} 个持仓")
        return result
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
