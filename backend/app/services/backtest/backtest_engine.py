"""
回测引擎基类
提供回测执行的核心功能：订单撮合、资金管理、持仓管理等
"""
from typing import Dict, List, Optional, Callable
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
from loguru import logger


@dataclass
class Trade:
    """交易记录"""
    timestamp: int  # 交易时间戳(毫秒)
    side: str  # 方向：buy/sell
    price: float  # 成交价格
    amount: float  # 成交数量
    fee: float  # 手续费
    position_before: float  # 交易前持仓
    position_after: float  # 交易后持仓
    capital_before: float  # 交易前资金
    capital_after: float  # 交易后资金
    pnl: float = 0.0  # 本次交易盈亏
    pnl_percent: float = 0.0  # 本次交易盈亏百分比


@dataclass
class Position:
    """持仓信息"""
    amount: float = 0.0  # 持仓数量
    avg_price: float = 0.0  # 平均成本价
    unrealized_pnl: float = 0.0  # 未实现盈亏


class BacktestEngine:
    """回测引擎基类"""

    def __init__(
        self,
        symbol: str,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,  # 默认手续费率 0.1%
    ):
        """
        初始化回测引擎

        Args:
            symbol: 交易对
            initial_capital: 初始资金(USDT)
            fee_rate: 手续费率
        """
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate

        # 账户状态
        self.capital = initial_capital  # 当前可用资金
        self.position = Position()  # 当前持仓

        # 交易记录
        self.trades: List[Trade] = []

        # 资金曲线
        self.equity_curve: List[Dict] = []

        # 当前K线索引
        self.current_index = 0
        self.current_kline: Optional[Dict] = None

    def reset(self):
        """重置回测状态"""
        self.capital = self.initial_capital
        self.position = Position()
        self.trades = []
        self.equity_curve = []
        self.current_index = 0
        self.current_kline = None

    def buy(self, price: float, amount: float, timestamp: int) -> Optional[Trade]:
        """
        买入

        Args:
            price: 买入价格
            amount: 买入数量
            timestamp: 时间戳

        Returns:
            交易记录，如果资金不足返回None
        """
        # 计算成本
        cost = price * amount
        fee = cost * self.fee_rate
        total_cost = cost + fee

        # 检查资金是否足够
        if total_cost > self.capital:
            logger.warning(f"资金不足: 需要 {total_cost:.2f}, 可用 {self.capital:.2f}")
            return None

        # 记录交易前状态
        position_before = self.position.amount
        capital_before = self.capital

        # 更新持仓（加权平均成本）
        if self.position.amount > 0:
            total_amount = self.position.amount + amount
            total_cost_basis = (self.position.avg_price * self.position.amount) + cost
            self.position.avg_price = total_cost_basis / total_amount
        else:
            self.position.avg_price = price

        self.position.amount += amount

        # 更新资金
        self.capital -= total_cost

        # 记录交易后状态
        position_after = self.position.amount
        capital_after = self.capital

        # 创建交易记录
        trade = Trade(
            timestamp=timestamp,
            side="buy",
            price=price,
            amount=amount,
            fee=fee,
            position_before=position_before,
            position_after=position_after,
            capital_before=capital_before,
            capital_after=capital_after,
            pnl=0.0,  # 买入时pnl为0
            pnl_percent=0.0
        )

        self.trades.append(trade)
        logger.debug(f"买入: {amount:.8f} @ {price:.2f}, 手续费: {fee:.4f}, 剩余资金: {self.capital:.2f}")

        return trade

    def sell(self, price: float, amount: float, timestamp: int) -> Optional[Trade]:
        """
        卖出

        Args:
            price: 卖出价格
            amount: 卖出数量
            timestamp: 时间戳

        Returns:
            交易记录，如果持仓不足返回None
        """
        # 检查持仓是否足够
        if amount > self.position.amount:
            logger.warning(f"持仓不足: 需要 {amount:.8f}, 可用 {self.position.amount:.8f}")
            return None

        # 计算收益
        revenue = price * amount
        fee = revenue * self.fee_rate
        net_revenue = revenue - fee

        # 计算盈亏
        cost_basis = self.position.avg_price * amount
        pnl = net_revenue - cost_basis
        pnl_percent = (pnl / cost_basis) * 100 if cost_basis > 0 else 0.0

        # 记录交易前状态
        position_before = self.position.amount
        capital_before = self.capital

        # 更新持仓
        self.position.amount -= amount
        if self.position.amount <= 0:
            self.position.amount = 0
            self.position.avg_price = 0

        # 更新资金
        self.capital += net_revenue

        # 记录交易后状态
        position_after = self.position.amount
        capital_after = self.capital

        # 创建交易记录
        trade = Trade(
            timestamp=timestamp,
            side="sell",
            price=price,
            amount=amount,
            fee=fee,
            position_before=position_before,
            position_after=position_after,
            capital_before=capital_before,
            capital_after=capital_after,
            pnl=pnl,
            pnl_percent=pnl_percent
        )

        self.trades.append(trade)
        logger.debug(f"卖出: {amount:.8f} @ {price:.2f}, 盈亏: {pnl:.2f} ({pnl_percent:.2f}%), 剩余资金: {self.capital:.2f}")

        return trade

    def update_equity(self, current_price: float, timestamp: int):
        """
        更新资金曲线

        Args:
            current_price: 当前价格
            timestamp: 时间戳
        """
        # 计算未实现盈亏
        if self.position.amount > 0:
            market_value = current_price * self.position.amount
            cost_basis = self.position.avg_price * self.position.amount
            self.position.unrealized_pnl = market_value - cost_basis
        else:
            self.position.unrealized_pnl = 0.0

        # 计算总权益
        total_equity = self.capital + (current_price * self.position.amount)

        # 记录到资金曲线
        self.equity_curve.append({
            "timestamp": timestamp,
            "equity": total_equity,
            "capital": self.capital,
            "position_value": current_price * self.position.amount,
            "unrealized_pnl": self.position.unrealized_pnl
        })

    def get_total_equity(self, current_price: float) -> float:
        """
        获取当前总权益

        Args:
            current_price: 当前价格

        Returns:
            总权益
        """
        return self.capital + (current_price * self.position.amount)

    def on_kline(self, kline: Dict):
        """
        处理K线数据（由子类实现策略逻辑）

        Args:
            kline: K线数据
        """
        raise NotImplementedError("子类必须实现 on_kline 方法")

    def run(self, klines: List[Dict], progress_callback: Optional[Callable] = None) -> Dict:
        """
        运行回测

        Args:
            klines: K线数据列表（按时间升序）
            progress_callback: 进度回调函数 callback(current, total)

        Returns:
            回测结果
        """
        logger.info(f"开始回测: {self.symbol}, 初始资金: {self.initial_capital}, K线数量: {len(klines)}")

        self.reset()

        total_klines = len(klines)

        for i, kline in enumerate(klines):
            self.current_index = i
            self.current_kline = kline

            # 调用策略逻辑
            self.on_kline(kline)

            # 更新资金曲线
            close_price = float(kline['close'])
            timestamp = int(kline['timestamp'])
            self.update_equity(close_price, timestamp)

            # 进度回调
            if progress_callback and i % 100 == 0:
                progress_callback(i + 1, total_klines)

        # 最终进度
        if progress_callback:
            progress_callback(total_klines, total_klines)

        # 计算最终权益
        if klines:
            final_price = float(klines[-1]['close'])
            final_equity = self.get_total_equity(final_price)
        else:
            final_equity = self.initial_capital

        logger.info(f"回测完成: 最终权益: {final_equity:.2f}, 交易次数: {len(self.trades)}")

        return {
            "final_equity": final_equity,
            "total_trades": len(self.trades),
            "initial_capital": self.initial_capital
        }
