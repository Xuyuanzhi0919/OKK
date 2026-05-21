"""
策略管理API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.database import get_db
from app.api.deps import require_current_user_id
from app.models.strategy import Strategy, StrategyStatus
from app.models.order import Order, OrderStatus, OrderSide
from app.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
    StrategyStatsResponse,
)
from app.services.strategy.manager import strategy_manager
from app.services.api_config_service import api_config_service
from app.core.config import settings
from typing import List
from datetime import datetime
from decimal import Decimal
from loguru import logger


router = APIRouter()


get_current_user_id = require_current_user_id


SUPPORTED_STRATEGY_TYPE = "adaptive_grid_trend"


@router.get("/", response_model=StrategyListResponse)
async def list_strategies(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取策略列表"""
    try:
        # 查询策略总数
        total = db.query(Strategy).filter(Strategy.user_id == user_id).count()

        # 查询策略列表
        strategies = (
            db.query(Strategy)
            .filter(Strategy.user_id == user_id)
            .order_by(desc(Strategy.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

        # 为每个策略动态计算统计数据
        strategy_responses = []
        for strategy in strategies:
            # 初始化默认统计数据
            total_profit = 0.0
            total_trades = 0
            win_rate = 0.0

            # 尝试从运行中的策略实例获取实时数据
            try:
                strategy_instance = strategy_manager.get_strategy(strategy.id)
                if strategy_instance and hasattr(strategy_instance, 'calculate_pnl'):
                    # 调用策略的calculate_pnl方法获取准确的盈亏数据
                    pnl_data = await strategy_instance.calculate_pnl()
                    total_profit = pnl_data.get("total_pnl", 0.0)
                    total_trades = pnl_data.get("buy_count", 0) + pnl_data.get("sell_count", 0)

                    # 计算胜率:已实现盈亏>0则算盈利
                    if total_trades > 0 and pnl_data.get("realized_pnl", 0) > 0:
                        # 简化计算:如果有盈利,胜率=盈利交易数/总交易数
                        # 更准确的计算需要记录每笔交易的盈亏
                        win_rate = 50.0  # 暂时使用固定值,后续优化
                else:
                    # 策略未运行,从数据库订单计算
                    filled_orders = (
                        db.query(Order)
                        .filter(
                            Order.strategy_id == strategy.id,
                            Order.status == OrderStatus.FILLED
                        )
                        .all()
                    )

                    total_trades = len(filled_orders)

                    # 简单计算:买卖配对
                    buy_total = Decimal('0')
                    sell_total = Decimal('0')
                    total_fee = Decimal('0')

                    for order in filled_orders:
                        if order.fee:
                            total_fee += Decimal(str(order.fee))

                        if order.avg_price and order.filled_amount:
                            amount_value = Decimal(str(order.avg_price)) * Decimal(str(order.filled_amount))
                            side = order.side.value if hasattr(order.side, 'value') else str(order.side)

                            if side.lower() == 'buy':
                                buy_total += amount_value
                            elif side.lower() == 'sell':
                                sell_total += amount_value

                    # 已实现盈亏 = 卖出总额 - 买入总额 - 手续费
                    total_profit = float(sell_total - buy_total - total_fee)

                    # 简单胜率:盈利则100%,亏损则0%
                    win_rate = 100.0 if total_profit > 0 else 0.0

            except Exception as calc_error:
                logger.warning(f"计算策略{strategy.id}统计数据失败: {calc_error}")
                # 使用默认值

            # 创建响应对象并更新统计数据
            strategy_dict = {
                'id': strategy.id,
                'user_id': strategy.user_id,
                'api_config_id': strategy.api_config_id,
                'name': strategy.name,
                'type': strategy.type,
                'symbol': strategy.symbol,
                'timeframe': strategy.timeframe,
                'status': strategy.status,
                'parameters': strategy.parameters,
                'description': strategy.description,
                'total_profit': total_profit,
                'total_trades': total_trades,
                'win_rate': round(win_rate, 2),
                'created_at': strategy.created_at,
                'updated_at': strategy.updated_at,
                'started_at': strategy.started_at,
                'stopped_at': strategy.stopped_at,
            }

            strategy_responses.append(StrategyResponse(**strategy_dict))

        return StrategyListResponse(
            total=total,
            items=strategy_responses
        )

    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取策略列表失败: {str(e)}"
        )


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    strategy_data: StrategyCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """创建策略"""
    try:
        # 将strategy_data.type转换为字符串值（小写）
        if isinstance(strategy_data.type, str):
            strategy_type_value = strategy_data.type
        else:
            # 如果是枚举对象，获取其value属性
            strategy_type_value = strategy_data.type.value if hasattr(strategy_data.type, 'value') else str(strategy_data.type).split('.')[-1].lower()

        logger.debug(f"策略类型转换: {strategy_data.type} -> {strategy_type_value}")

        if strategy_type_value != SUPPORTED_STRATEGY_TYPE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="后端当前仅支持自适应趋势网格策略"
            )

        bound_api_config = None
        if strategy_data.api_config_id is not None:
            bound_api_config = api_config_service.get_config(
                user_id=user_id,
                config_id=strategy_data.api_config_id,
                db=db,
            )
            if not bound_api_config:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="绑定的API配置不存在"
                )
            if not bound_api_config.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"绑定的API配置无效: {bound_api_config.error_message or '请先验证配置'}"
                )

        db_strategy = Strategy(
            user_id=user_id,
            api_config_id=strategy_data.api_config_id,
            name=strategy_data.name,
            type=strategy_type_value,
            symbol=strategy_data.symbol,
            timeframe=strategy_data.timeframe,
            parameters=strategy_data.parameters,
            description=strategy_data.description,
            status='stopped',  # 直接使用小写字符串
        )

        db.add(db_strategy)
        db.commit()
        db.refresh(db_strategy)

        logger.info(f"创建策略成功: ID={db_strategy.id}, 名称={db_strategy.name}")

        return StrategyResponse.model_validate(db_strategy)

    except HTTPException:
        # 重新抛出HTTPException（包括余额不足的错误）
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"创建策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建策略失败: {str(e)}"
        )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取策略详情"""
    strategy = (
        db.query(Strategy)
        .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
        .first()
    )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"策略 {strategy_id} 不存在"
        )

    return StrategyResponse.model_validate(strategy)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy_data: StrategyUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """更新策略"""
    try:
        # 查询策略
        strategy = (
            db.query(Strategy)
            .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .first()
        )

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"策略 {strategy_id} 不存在"
            )

        # 检查策略是否在运行
        if strategy.status == StrategyStatus.RUNNING.value or strategy.status == 'running':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="策略正在运行，无法修改"
            )

        # 更新字段
        update_data = strategy_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(strategy, field, value)

        strategy.updated_at = datetime.now()

        db.commit()
        db.refresh(strategy)

        logger.info(f"更新策略成功: ID={strategy_id}")

        return StrategyResponse.model_validate(strategy)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新策略失败: {str(e)}"
        )


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """删除策略（会自动撤销所有未成交订单）"""
    from app.models.order import Order, OrderStatus as OS
    from app.services.api_config_service import api_config_service
    from datetime import datetime, timezone

    try:
        # 查询策略
        strategy = (
            db.query(Strategy)
            .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .first()
        )

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"策略 {strategy_id} 不存在"
            )

        # 若策略正在运行，先停止并平仓，再执行删除
        if strategy.status == StrategyStatus.RUNNING.value or strategy.status == 'running':
            logger.info(f"删除前自动停止并平仓策略 {strategy_id}")
            try:
                await strategy_manager.stop_strategy(strategy_id, cancel_orders=True, close_position=True)
            except Exception as e:
                logger.warning(f"删除时停止策略 {strategy_id} 失败（继续删除）: {e}")

        # 删除前先撤销所有未成交订单（安全措施）
        pending_orders = db.query(Order).filter(
            Order.strategy_id == strategy_id,
            Order.status.in_([OS.PENDING, OS.SUBMITTED, OS.PARTIAL_FILLED])
        ).all()

        cancel_count = 0
        if pending_orders:
            logger.info(f"删除策略前撤销 {len(pending_orders)} 个未成交订单")

            # 获取策略绑定的交易所实例；旧策略未绑定时回退到当前激活配置
            exchange = api_config_service.get_exchange(
                user_id=user_id,
                config_id=strategy.api_config_id,
            )

            for order in pending_orders:
                try:
                    await exchange.cancel_order(
                        symbol=order.symbol,
                        order_id=order.order_id
                    )
                    order.status = OS.CANCELED
                    order.canceled_at = datetime.now(timezone.utc)
                    cancel_count += 1
                    logger.info(f"✓ 撤销订单: {order.order_id}")
                except Exception as e:
                    logger.warning(f"撤销订单 {order.order_id} 失败: {e} (将继续删除)")

            await exchange.close()
            db.commit()

        # 删除策略
        db.delete(strategy)
        db.commit()

        logger.info(f"删除策略成功: ID={strategy_id}, 撤销订单: {cancel_count} 个")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除策略失败: {str(e)}"
        )


@router.post("/{strategy_id}/start", response_model=StrategyResponse)
async def start_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """启动策略"""
    try:
        # 查询策略
        strategy = (
            db.query(Strategy)
            .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .first()
        )

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"策略 {strategy_id} 不存在"
            )

        # 检查策略状态
        if strategy.status == StrategyStatus.RUNNING.value or strategy.status == 'running':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="策略已在运行中"
            )

        strategy_type_value = strategy.type.value if hasattr(strategy.type, 'value') else str(strategy.type)
        if strategy_type_value != SUPPORTED_STRATEGY_TYPE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="后端当前仅支持启动自适应趋势网格策略"
            )

        # 获取交易所实例（优先使用数据库配置，否则使用.env配置）
        try:
            exchange = api_config_service.get_exchange(
                user_id=user_id,
                config_id=strategy.api_config_id,
            )
            logger.info(f"策略使用数据库API配置启动")
        except Exception as e:
            logger.warning(f"获取数据库API配置失败，使用.env配置: {e}")
            exchange = strategy_manager.get_exchange(
                api_key=settings.OKX_API_KEY,
                secret_key=settings.OKX_SECRET_KEY,
                passphrase=settings.OKX_PASSPHRASE
            )

        # 启动策略
        success = await strategy_manager.start_strategy(
            strategy_id=strategy.id,
            strategy_type=strategy.type,
            symbol=strategy.symbol,
            parameters=strategy.parameters or {},
            exchange=exchange,
            user_id=user_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="启动策略失败"
            )

        # 更新策略状态
        strategy.status = 'running'  # 直接使用字符串
        strategy.started_at = datetime.now()
        db.commit()
        db.refresh(strategy)

        logger.info(f"启动策略成功: ID={strategy_id}")

        return StrategyResponse.model_validate(strategy)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"启动策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动策略失败: {str(e)}"
        )


@router.post("/{strategy_id}/stop", response_model=StrategyResponse)
async def stop_strategy(
    strategy_id: int,
    cancel_orders: bool = True,
    close_position: bool = True,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    停止策略

    Args:
        strategy_id: 策略ID
        cancel_orders: 是否撤销所有未成交订单，默认True
        close_position: 是否市价平掉当前持仓，默认True
    """
    try:
        # 查询策略
        strategy = (
            db.query(Strategy)
            .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .first()
        )

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"策略 {strategy_id} 不存在"
            )

        # 检查策略状态
        if strategy.status != StrategyStatus.RUNNING.value and strategy.status != 'running':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="策略未在运行"
            )

        # 停止策略（传递 cancel_orders / close_position 参数）
        success = await strategy_manager.stop_strategy(
            strategy_id, cancel_orders=cancel_orders, close_position=close_position
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="停止策略失败"
            )

        # 更新策略状态
        strategy.status = 'stopped'  # 直接使用字符串
        strategy.stopped_at = datetime.now()
        db.commit()
        db.refresh(strategy)

        logger.info(f"停止策略成功: ID={strategy_id}")

        return StrategyResponse.model_validate(strategy)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"停止策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停止策略失败: {str(e)}"
        )


@router.get("/{strategy_id}/stats", response_model=StrategyStatsResponse)
async def get_strategy_stats(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取策略实时统计信息"""
    try:
        # 查询策略
        strategy = (
            db.query(Strategy)
            .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .first()
        )

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"策略 {strategy_id} 不存在"
            )

        # 获取运行时统计
        stats = strategy_manager.get_strategy_stats(strategy_id)

        if stats:
            return StrategyStatsResponse(**stats)
        else:
            # 策略未运行，返回基础信息
            return StrategyStatsResponse(
                strategy_id=strategy_id,
                is_running=False
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取策略统计失败: {str(e)}"
        )


@router.get("/{strategy_id}/orders")
async def get_strategy_orders(
    strategy_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取策略的交易历史记录"""
    try:
        from app.models.order import Order

        # 验证策略存在且属于当前用户
        strategy = (
            db.query(Strategy)
            .filter(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .first()
        )

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"策略 {strategy_id} 不存在"
            )

        # 查询订单总数
        total = db.query(Order).filter(Order.strategy_id == strategy_id).count()

        # 查询订单列表（按创建时间倒序）
        orders = (
            db.query(Order)
            .filter(Order.strategy_id == strategy_id)
            .order_by(desc(Order.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

        # 转换为字典格式
        order_list = []
        for order in orders:
            order_list.append({
                "id": order.id,
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value if hasattr(order.side, 'value') else order.side,
                "order_type": order.order_type.value if hasattr(order.order_type, 'value') else order.order_type,
                "status": order.status.value if hasattr(order.status, 'value') else order.status,
                "price": order.price,
                "amount": order.amount,
                "filled_amount": order.filled_amount,
                "avg_price": order.avg_price,
                "fee": order.fee,
                "fee_currency": order.fee_currency,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "canceled_at": order.canceled_at.isoformat() if order.canceled_at else None,
                "note": order.note,
            })

        return {
            "code": 0,
            "msg": "success",
            "data": {
                "total": total,
                "items": order_list
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略交易历史失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取策略交易历史失败: {str(e)}"
        )


@router.get("/{strategy_id}/performance")
async def get_strategy_performance(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取策略性能统计(优化版:使用策略实例的calculate_pnl)"""
    from app.models.order import Order, OrderStatus, OrderSide
    from sqlalchemy import func, case
    from decimal import Decimal

    # 验证策略所有权
    strategy = db.query(Strategy).filter(
        Strategy.id == strategy_id,
        Strategy.user_id == user_id
    ).first()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在"
        )

    # 优先使用策略实例的calculate_pnl获取准确数据
    try:
        strategy_instance = strategy_manager.get_strategy(strategy_id)
        if strategy_instance and hasattr(strategy_instance, 'calculate_pnl'):
            pnl_data = await strategy_instance.calculate_pnl()

            # 使用策略实例的盈亏数据
            total_profit = pnl_data.get("total_pnl", 0.0)
            realized_profit = pnl_data.get("realized_pnl", 0.0)
            unrealized_profit = pnl_data.get("unrealized_pnl", 0.0)
            total_fee = pnl_data.get("total_fee", 0.0)
            buy_count = pnl_data.get("buy_count", 0)
            sell_count = pnl_data.get("sell_count", 0)
            in_position = bool(pnl_data.get("in_position", False))
            position_side = pnl_data.get("position_side", "")

            # 计算总交易次数和收益率
            total_trades = int(pnl_data.get("total_trades", buy_count + sell_count))
            total_orders = int(pnl_data.get("total_orders", buy_count + sell_count))
            if strategy.parameters:
                base_amount = Decimal(str(
                    strategy.parameters.get("initial_amount")
                    or strategy.parameters.get("risk_base_usd")
                    or strategy.parameters.get("max_position_usd")
                    or 0
                ))
                total_profit_rate = (Decimal(str(total_profit)) / base_amount * 100) if base_amount > 0 else Decimal('0')
            else:
                total_profit_rate = Decimal('0')

            # 简化胜率计算
            win_rate = float(pnl_data.get("win_rate", 100.0 if realized_profit > 0 else 0.0 if total_trades > 0 else 0.0))

            logger.info(f"使用策略实例计算性能: total_pnl={total_profit}, realized={realized_profit}, unrealized={unrealized_profit}")

            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "strategy_id": strategy_id,
                    "total_profit": float(total_profit),
                    "total_profit_rate": float(total_profit_rate),
                    "realized_profit": float(realized_profit),
                    "unrealized_profit": float(unrealized_profit),
                    "total_trades": total_trades,
                    "total_orders": total_orders,
                    "in_position": in_position,
                    "position_side": position_side,
                    "successful_trades": buy_count if realized_profit > 0 else 0,
                    "failed_trades": 0,
                    "win_rate": win_rate,
                    "total_fee": float(total_fee),
                    "max_drawdown": 0,
                    "profit_history": [],
                    "daily_profits": []
                }
            }
    except Exception as e:
        logger.warning(f"使用策略实例计算失败,回退到订单计算: {e}")

    # 回退方案:从订单计算(保留原有逻辑)

    # 获取所有已成交订单
    filled_orders = db.query(Order).filter(
        Order.strategy_id == strategy_id,
        Order.status == OrderStatus.FILLED.value
    ).order_by(Order.filled_at).all()

    if not filled_orders:
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "strategy_id": strategy_id,
                "total_profit": 0,
                "total_profit_rate": 0,
                "realized_profit": 0,
                "unrealized_profit": 0,
                "total_trades": 0,
                "successful_trades": 0,
                "failed_trades": 0,
                "win_rate": 0,
                "total_fee": 0,
                "max_drawdown": 0,
                "profit_history": [],
                "daily_profits": []
            }
        }

    # 计算已实现盈亏 (配对买卖单)
    buy_orders = [o for o in filled_orders if o.side == OrderSide.BUY.value]
    sell_orders = [o for o in filled_orders if o.side == OrderSide.SELL.value]

    realized_profit = Decimal('0')
    successful_trades = 0
    failed_trades = 0
    total_fee = Decimal('0')

    # 简单配对: 按时间顺序配对买卖单
    paired_count = min(len(buy_orders), len(sell_orders))
    for i in range(paired_count):
        buy_order = buy_orders[i]
        sell_order = sell_orders[i]

        buy_cost = Decimal(str(buy_order.avg_price or buy_order.price)) * Decimal(str(buy_order.filled_amount))
        sell_income = Decimal(str(sell_order.avg_price or sell_order.price)) * Decimal(str(sell_order.filled_amount))

        profit = sell_income - buy_cost
        realized_profit += profit

        total_fee += Decimal(str(buy_order.fee or 0)) + Decimal(str(sell_order.fee or 0))

        if profit > 0:
            successful_trades += 1
        else:
            failed_trades += 1

    # 计算未实现盈亏 (未配对的订单)
    unrealized_profit = Decimal('0')
    unpaired_buy = len(buy_orders) - paired_count
    unpaired_sell = len(sell_orders) - paired_count

    # 获取当前价格估算未实现盈亏
    try:
        from app.api.endpoints.market import get_public_okx_exchange
        exchange = get_public_okx_exchange()
        ticker = await exchange.get_ticker(strategy.symbol)
        current_price = Decimal(str(ticker.get("last", 0)))
        await exchange.close()

        # 多余的买单(持仓),用当前价格估值
        for i in range(paired_count, len(buy_orders)):
            buy_order = buy_orders[i]
            buy_cost = Decimal(str(buy_order.avg_price or buy_order.price)) * Decimal(str(buy_order.filled_amount))
            current_value = current_price * Decimal(str(buy_order.filled_amount))
            unrealized_profit += (current_value - buy_cost)
    except Exception as e:
        logger.warning(f"获取当前价格失败,未实现盈亏设为0: {e}")

    # 总盈亏
    total_profit = realized_profit + unrealized_profit - total_fee

    # 计算收益率 (基于策略投资金额)
    if strategy.parameters and 'total_amount' in strategy.parameters:
        total_amount = Decimal(str(strategy.parameters['total_amount']))
        total_profit_rate = (total_profit / total_amount * 100) if total_amount > 0 else Decimal('0')
    else:
        total_profit_rate = Decimal('0')

    # 胜率
    total_completed = successful_trades + failed_trades
    win_rate = (successful_trades / total_completed * 100) if total_completed > 0 else 0

    # 盈亏历史 (累计盈亏曲线)
    profit_history = []
    cumulative_profit = Decimal('0')

    for i in range(paired_count):
        buy_order = buy_orders[i]
        sell_order = sell_orders[i]

        buy_cost = Decimal(str(buy_order.avg_price or buy_order.price)) * Decimal(str(buy_order.filled_amount))
        sell_income = Decimal(str(sell_order.avg_price or sell_order.price)) * Decimal(str(sell_order.filled_amount))
        profit = sell_income - buy_cost

        cumulative_profit += profit

        profit_history.append({
            "timestamp": sell_order.filled_at.isoformat() if sell_order.filled_at else None,
            "profit": float(profit),
            "cumulative_profit": float(cumulative_profit)
        })

    # 按日统计盈亏
    daily_profits = {}
    for record in profit_history:
        if record["timestamp"]:
            date = record["timestamp"][:10]  # YYYY-MM-DD
            if date not in daily_profits:
                daily_profits[date] = 0
            daily_profits[date] += record["profit"]

    daily_profits_list = [
        {"date": date, "profit": profit}
        for date, profit in sorted(daily_profits.items())
    ]

    # 计算最大回撤
    max_drawdown = Decimal('0')
    peak = Decimal('0')
    for record in profit_history:
        current = Decimal(str(record["cumulative_profit"]))
        if current > peak:
            peak = current
        drawdown = peak - current
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return {
        "code": 0,
        "msg": "success",
        "data": {
            "strategy_id": strategy_id,
            "total_profit": float(total_profit),
            "total_profit_rate": float(total_profit_rate),
            "realized_profit": float(realized_profit),
            "unrealized_profit": float(unrealized_profit),
            "total_trades": len(filled_orders),
            "successful_trades": successful_trades,
            "failed_trades": failed_trades,
            "win_rate": round(win_rate, 2),
            "total_fee": float(total_fee),
            "max_drawdown": float(max_drawdown),
            "profit_history": profit_history,
            "daily_profits": daily_profits_list
        }
    }


@router.get("/{strategy_id}/pnl")
async def get_strategy_pnl(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    获取策略的实时盈亏统计

    Returns:
        {
            "total_pnl": 总盈亏 (USDT),
            "realized_pnl": 已实现盈亏,
            "unrealized_pnl": 未实现盈亏,
            "total_fee": 总手续费,
            "pnl_rate": 收益率 (%),
            "buy_count": 买入成交次数,
            "sell_count": 卖出成交次数,
            ...
        }
    """
    try:
        # 检查策略是否存在且属于当前用户
        strategy = db.query(Strategy).filter(
            Strategy.id == strategy_id,
            Strategy.user_id == user_id
        ).first()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="策略不存在"
            )

        # 从策略管理器获取运行中的策略实例
        strategy_instance = strategy_manager.get_strategy(strategy_id)

        if strategy_instance:
            # 策略正在运行,直接计算盈亏
            pnl_data = await strategy_instance.calculate_pnl()
            return pnl_data
        else:
            # 策略未运行,返回数据库中存储的盈亏数据
            return {
                "total_pnl": strategy.total_profit or 0,
                "realized_pnl": strategy.total_profit or 0,
                "unrealized_pnl": 0,
                "total_fee": 0,
                "pnl_rate": 0,
                "buy_count": 0,
                "sell_count": 0,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略盈亏失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取盈亏数据失败: {str(e)}"
        )


@router.post("/{strategy_id}/backtest")
async def backtest_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """回测策略"""
    # TODO: 实现回测逻辑
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="回测功能尚未实现"
    )
