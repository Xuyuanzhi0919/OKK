"""
回测执行服务
负责协调K线数据、回测引擎和结果存储
"""
from typing import Dict, Optional
from sqlalchemy.orm import Session
from loguru import logger
from datetime import datetime

from app.models import Backtest, BacktestTrade, Kline
from .kline_service import KlineService
from .grid_backtest import GridBacktestEngine, GridMarketMakingBacktest
from .metrics import BacktestMetrics


class BacktestService:
    """回测执行服务"""

    def __init__(self, db: Session):
        """
        初始化回测服务

        Args:
            db: 数据库会话
        """
        self.db = db

    def create_backtest(
        self,
        user_id: int,
        name: str,
        strategy_type: str,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        initial_capital: float,
        parameters: Dict,
        description: Optional[str] = None
    ) -> Backtest:
        """
        创建回测记录

        Args:
            user_id: 用户ID
            name: 回测名称
            strategy_type: 策略类型 (grid/grid_mm)
            symbol: 交易对
            interval: K线周期
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            initial_capital: 初始资金
            parameters: 策略参数
            description: 回测描述

        Returns:
            回测记录
        """
        backtest = Backtest(
            user_id=user_id,
            name=name,
            description=description,
            strategy_type=strategy_type,
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            initial_capital=initial_capital,
            parameters=parameters,
            status='pending',
            progress=0
        )

        self.db.add(backtest)
        self.db.commit()
        self.db.refresh(backtest)

        logger.info(f"创建回测记录: ID={backtest.id}, 策略={strategy_type}, 交易对={symbol}")

        return backtest

    async def run_backtest(self, backtest_id: int) -> Dict:
        """
        执行回测

        Args:
            backtest_id: 回测ID

        Returns:
            回测结果
        """
        # 获取回测记录
        backtest = self.db.query(Backtest).filter(Backtest.id == backtest_id).first()
        if not backtest:
            raise ValueError(f"回测记录不存在: {backtest_id}")

        try:
            # 更新状态为运行中
            backtest.status = 'running'
            backtest.progress = 0
            self.db.commit()

            logger.info(f"开始执行回测: ID={backtest_id}, 策略={backtest.strategy_type}")

            # 获取K线数据
            kline_service = KlineService(self.db, None)  # 不需要exchange
            klines = kline_service.query_klines(
                symbol=backtest.symbol,
                interval=backtest.interval,
                start_time=backtest.start_time,
                end_time=backtest.end_time
            )

            if not klines:
                raise ValueError("没有K线数据，请先获取历史数据")

            logger.info(f"加载K线数据: {len(klines)} 条")

            # 转换为字典格式
            kline_dicts = [
                {
                    "timestamp": k.timestamp,
                    "open": float(k.open),
                    "high": float(k.high),
                    "low": float(k.low),
                    "close": float(k.close),
                    "volume": float(k.volume),
                    "volume_currency": float(k.volume_currency)
                }
                for k in klines
            ]

            # 创建回测引擎
            engine = self._create_engine(backtest)

            # 进度回调
            def progress_callback(current, total):
                progress = int((current / total) * 100)
                backtest.progress = progress
                self.db.commit()
                logger.debug(f"回测进度: {progress}%")

            # 运行回测
            result = engine.run(kline_dicts, progress_callback)

            # 计算性能指标
            metrics = BacktestMetrics.calculate_all_metrics(
                initial_capital=float(backtest.initial_capital),
                final_capital=result['final_equity'],
                equity_curve=engine.equity_curve,
                trades=[self._trade_to_dict(t) for t in engine.trades],
                start_timestamp=backtest.start_time,
                end_timestamp=backtest.end_time
            )

            # 保存回测结果
            backtest.status = 'completed'
            backtest.progress = 100
            backtest.final_capital = result['final_equity']
            backtest.total_return = metrics['total_return']
            backtest.annualized_return = metrics['annualized_return']
            backtest.max_drawdown = metrics['max_drawdown']
            backtest.sharpe_ratio = metrics['sharpe_ratio']
            backtest.total_trades = metrics['total_trades']
            backtest.winning_trades = metrics['winning_trades']
            backtest.losing_trades = metrics['losing_trades']
            backtest.win_rate = metrics['win_rate']
            backtest.profit_factor = metrics['profit_factor']
            backtest.total_fee = metrics['total_fee']
            backtest.equity_curve = engine.equity_curve
            backtest.completed_at = datetime.now()

            # 保存交易记录
            for trade in engine.trades:
                backtest_trade = BacktestTrade(
                    backtest_id=backtest.id,
                    timestamp=trade.timestamp,
                    side=trade.side,
                    price=trade.price,
                    amount=trade.amount,
                    fee=trade.fee,
                    position_before=trade.position_before,
                    position_after=trade.position_after,
                    capital_before=trade.capital_before,
                    capital_after=trade.capital_after,
                    pnl=trade.pnl,
                    pnl_percent=trade.pnl_percent
                )
                self.db.add(backtest_trade)

            self.db.commit()

            logger.info(f"回测完成: ID={backtest_id}, "
                       f"最终资金={result['final_equity']:.2f}, "
                       f"收益率={metrics['total_return']*100:.2f}%")

            return {
                "backtest_id": backtest.id,
                "status": "completed",
                "metrics": metrics,
                "final_equity": result['final_equity']
            }

        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            backtest.status = 'failed'
            backtest.error_message = str(e)
            self.db.commit()
            raise

    def _create_engine(self, backtest: Backtest):
        """
        根据策略类型创建回测引擎

        Args:
            backtest: 回测记录

        Returns:
            回测引擎实例
        """
        params = backtest.parameters or {}

        if backtest.strategy_type == 'grid':
            # 网格策略
            return GridBacktestEngine(
                symbol=backtest.symbol,
                initial_capital=float(backtest.initial_capital),
                grid_lower=float(params.get('grid_lower', 50000)),
                grid_upper=float(params.get('grid_upper', 60000)),
                grid_num=int(params.get('grid_num', 10)),
                amount_per_grid=float(params.get('amount_per_grid', 0.001)),
                fee_rate=float(params.get('fee_rate', 0.001))
            )
        elif backtest.strategy_type == 'grid_mm':
            # 网格做市策略
            return GridMarketMakingBacktest(
                symbol=backtest.symbol,
                initial_capital=float(backtest.initial_capital),
                grid_spread=float(params.get('grid_spread', 0.01)),
                grid_levels=int(params.get('grid_levels', 5)),
                amount_per_grid=float(params.get('amount_per_grid', 0.001)),
                fee_rate=float(params.get('fee_rate', 0.001))
            )
        else:
            raise ValueError(f"不支持的策略类型: {backtest.strategy_type}")

    @staticmethod
    def _trade_to_dict(trade) -> Dict:
        """
        将Trade对象转换为字典

        Args:
            trade: Trade对象

        Returns:
            字典
        """
        return {
            "timestamp": trade.timestamp,
            "side": trade.side,
            "price": trade.price,
            "amount": trade.amount,
            "fee": trade.fee,
            "pnl": trade.pnl,
            "pnl_percent": trade.pnl_percent
        }
