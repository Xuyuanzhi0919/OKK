"""
趋势跟踪策略 - EMA 双均线交叉（已优化）

最优参数（经 256 组网格搜索 + 交叉验证）：
  EMA 快线: 12
  EMA 慢线: 40
  止损:     1.0%（由实时 Ticker 价格触发）
  止盈:     8.0%（由实时 Ticker 价格触发）
  过滤:     RSI14 < 65（开仓前检查，过滤超买）
  方向:     Long-only（15m 时间周期最优）

信号逻辑：
  - 每 15 分钟取一次已确认 K 线的收盘价更新 EMA
  - 金叉（fast 上穿 slow）且 RSI < 65 → 开多
  - 死叉（fast 下穿 slow）→ 平多
  - 实时 Ticker 价格触发止损/止盈（无需等 K 线关闭）
"""
import time
from typing import Dict, List, Optional
from decimal import Decimal
from loguru import logger

from app.services.strategy.base import StrategyBase


# ── 最优超参数（不可随意修改，来自回测验证） ─────────────────────────
_FAST_PERIOD    = 12
_SLOW_PERIOD    = 40
_RSI_PERIOD     = 14
_RSI_THRESHOLD  = 65.0      # RSI 超过此值不开仓（超买过滤）
_TIMEFRAME      = "15m"
_KLINE_LIMIT    = 80        # 预热 K 线数（>= slow_period + warmup）
_LOOP_SECONDS   = 15 * 60  # 15 分钟换一次 K 线周期


class TrendFollowStrategy(StrategyBase):
    """
    EMA 双均线趋势跟踪策略（实盘版）

    支持通过 parameters 字典覆盖默认参数：
      - fast_period:   EMA 快线周期（默认 12）
      - slow_period:   EMA 慢线周期（默认 40）
      - stop_loss:     止损比例（默认 0.01 = 1%）
      - take_profit:   止盈比例（默认 0.08 = 8%）
      - position_ratio: 每次开仓占可用资金的比例（默认 0.4 = 40%）
      - use_rsi_filter: 是否启用 RSI 过滤（默认 True）
      - rsi_threshold:  RSI 阈值（默认 65.0）
    """

    def __init__(
        self,
        strategy_id: int,
        exchange,
        symbol: str,
        parameters: Dict,
        user_id: int = 1,
    ):
        super().__init__(strategy_id, exchange, symbol, parameters, user_id)

        p = parameters or {}
        self.fast_period:   int   = int(p.get("fast_period",   _FAST_PERIOD))
        self.slow_period:   int   = int(p.get("slow_period",   _SLOW_PERIOD))
        self.stop_loss:     float = float(p.get("stop_loss",    0.01))
        self.take_profit:   float = float(p.get("take_profit",  0.08))
        self.pos_ratio:     float = float(p.get("position_ratio", 0.4))
        self.use_rsi:       bool  = bool(p.get("use_rsi_filter", True))
        self.rsi_threshold: float = float(p.get("rsi_threshold",  _RSI_THRESHOLD))

        # EMA 状态（仅保留最近两个值用于交叉判断）
        self._fast_prev: Optional[float] = None
        self._fast_curr: Optional[float] = None
        self._slow_prev: Optional[float] = None
        self._slow_curr: Optional[float] = None

        # 仓位状态
        self._in_position: bool = False
        self._entry_price:  float = 0.0
        self._position_qty: float = 0.0   # 持仓数量（合约张数 or 币数）

        # K 线周期追踪（毫秒级时间戳，以 15min 对齐）
        self._last_kline_period: int = 0

        # 统计数据（供 manager 广播）
        self.realized_pnl: float = 0.0
        self.total_trades: int   = 0
        self._win_trades:  int   = 0
        self.win_rate:     float = 0.0

        logger.info(
            f"TrendFollowStrategy 初始化: {symbol} "
            f"fast={self.fast_period} slow={self.slow_period} "
            f"sl={self.stop_loss*100:.1f}% tp={self.take_profit*100:.1f}% "
            f"RSI过滤={'是' if self.use_rsi else '否'}"
        )

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    async def start(self):
        self.is_running = True
        self._in_position = False
        self._entry_price = 0.0
        self._position_qty = 0.0
        self._last_kline_period = 0

        # 用历史 K 线预热 EMA
        await self._init_ema()
        logger.info(f"策略 {self.strategy_id} [{self.symbol}] 已启动")

    async def stop(self, cancel_orders: bool = True):
        self.is_running = False
        if self._in_position:
            await self._close_position(reason="stop")
        logger.info(f"策略 {self.strategy_id} [{self.symbol}] 已停止")

    # ═══════════════════════════════════════════════════════════
    # 核心 Tick 回调（由 manager 每 5 秒调用）
    # ═══════════════════════════════════════════════════════════

    async def on_tick(self, ticker: Dict):
        """
        每 5 秒由 manager 调用一次。
        1. 用实时价格检查止损/止盈（快速响应）。
        2. 每 15 分钟刷新一次 EMA 并检查交叉信号。
        """
        if not self.is_running:
            return

        price = float(ticker.get("last", 0))
        if price <= 0:
            return

        # ── 止损 / 止盈（实时触发）───────────────────────────────
        if self._in_position and self._entry_price > 0:
            pnl_pct = (price - self._entry_price) / self._entry_price
            if pnl_pct <= -self.stop_loss:
                logger.info(f"[{self.symbol}] 触发止损 {pnl_pct*100:.2f}%")
                await self._close_position(reason="stop_loss")
                return
            if pnl_pct >= self.take_profit:
                logger.info(f"[{self.symbol}] 触发止盈 {pnl_pct*100:.2f}%")
                await self._close_position(reason="take_profit")
                return

        # ── 15 分钟 K 线信号（每周期只处理一次）──────────────────
        now_ms = int(time.time() * 1000)
        period_ms = 15 * 60 * 1000
        current_period = (now_ms // period_ms) * period_ms

        if current_period != self._last_kline_period:
            self._last_kline_period = current_period
            await self._process_kline_signal()

    async def on_kline(self, kline: Dict):
        """K 线推送回调（当前架构未使用，保留接口兼容）"""
        pass

    async def on_order_update(self, order: Dict):
        """订单成交回调（当前策略使用市价单，无需额外处理）"""
        logger.debug(f"[{self.symbol}] 订单更新: {order.get('order_id')} status={order.get('status')}")

    # ═══════════════════════════════════════════════════════════
    # 信号逻辑
    # ═══════════════════════════════════════════════════════════

    async def _process_kline_signal(self):
        """获取已确认 K 线，更新 EMA，检测金叉/死叉并下单"""
        try:
            klines = await self.exchange.get_kline(self.symbol, _TIMEFRAME, _KLINE_LIMIT)
        except Exception as e:
            logger.error(f"[{self.symbol}] 获取 K 线失败: {e}")
            return

        if not klines or len(klines) < self.slow_period + 2:
            logger.warning(f"[{self.symbol}] K 线数据不足: {len(klines) if klines else 0}")
            return

        # 取倒数第 2 根（最后一根可能未完成）
        confirmed = klines[:-1]
        closes = [float(k["close"]) for k in confirmed]

        self._update_ema_from_closes(closes)

        if self._fast_curr is None or self._slow_curr is None:
            return

        golden = (self._fast_prev is not None and
                  self._slow_prev is not None and
                  self._fast_prev <= self._slow_prev and
                  self._fast_curr > self._slow_curr)

        death = (self._fast_prev is not None and
                 self._slow_prev is not None and
                 self._fast_prev >= self._slow_prev and
                 self._fast_curr < self._slow_curr)

        current_price = float(klines[-1]["close"])

        if golden and not self._in_position:
            if self.use_rsi and self._rsi(closes) >= self.rsi_threshold:
                logger.info(f"[{self.symbol}] 金叉但 RSI 超买，跳过开仓")
                return
            await self._open_position(current_price)

        elif death and self._in_position:
            await self._close_position(reason="death_cross")

    # ═══════════════════════════════════════════════════════════
    # EMA 计算
    # ═══════════════════════════════════════════════════════════

    def _update_ema_from_closes(self, closes: List[float]):
        """从历史收盘价序列重新计算 EMA，保留最后两个值用于交叉判断"""
        if len(closes) < self.slow_period:
            return

        fast_k = 2 / (self.fast_period + 1)
        slow_k = 2 / (self.slow_period + 1)

        # 用前 slow_period 根做 SMA 初始化
        fast_ema = sum(closes[:self.fast_period]) / self.fast_period
        slow_ema = sum(closes[:self.slow_period]) / self.slow_period

        prev_fast = fast_ema
        prev_slow = slow_ema

        for price in closes[self.slow_period:]:
            prev_fast, fast_ema = fast_ema, (price - fast_ema) * fast_k + fast_ema
            prev_slow, slow_ema = slow_ema, (price - slow_ema) * slow_k + slow_ema

        self._fast_prev = prev_fast
        self._fast_curr = fast_ema
        self._slow_prev = prev_slow
        self._slow_curr = slow_ema

    async def _init_ema(self):
        """启动时用历史 K 线预热 EMA"""
        try:
            klines = await self.exchange.get_kline(self.symbol, _TIMEFRAME, _KLINE_LIMIT)
            if klines and len(klines) >= self.slow_period + 2:
                closes = [float(k["close"]) for k in klines[:-1]]
                self._update_ema_from_closes(closes)
                logger.info(
                    f"[{self.symbol}] EMA 预热完成: fast={self._fast_curr:.2f} slow={self._slow_curr:.2f}"
                )
        except Exception as e:
            logger.warning(f"[{self.symbol}] EMA 预热失败（首次 tick 时会重试）: {e}")

    @staticmethod
    def _rsi(closes: List[float], period: int = _RSI_PERIOD) -> float:
        """计算 RSI"""
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(-period, 0):
            d = closes[i] - closes[i - 1]
            (gains if d > 0 else losses).append(abs(d))
        avg_g = sum(gains) / period
        avg_l = sum(losses) / period
        if avg_l == 0:
            return 100.0
        return 100.0 - 100.0 / (1 + avg_g / avg_l)

    # ═══════════════════════════════════════════════════════════
    # 开平仓
    # ═══════════════════════════════════════════════════════════

    async def _open_position(self, price: float):
        """开多仓（市价）"""
        try:
            balance = await self.exchange.get_balance()
            # 取 USDT 可用余额
            usdt = balance.get("USDT", {})
            available = float(usdt.get("free", usdt.get("available", 0)))
            if available <= 0:
                logger.warning(f"[{self.symbol}] 可用余额不足，跳过开仓")
                return

            qty = available * self.pos_ratio / price
            qty = round(qty, 6)
            if qty <= 0:
                return

            order = await self.place_order_with_retry(
                side="buy",
                amount=Decimal(str(qty)),
                order_type="market",
            )
            if order:
                self._in_position = True
                self._entry_price = price
                self._position_qty = qty
                logger.info(
                    f"[{self.symbol}] 开多 qty={qty:.6f} @ {price:.2f} "
                    f"RSI={self._rsi.__name__}"
                )
        except Exception as e:
            logger.error(f"[{self.symbol}] 开多失败: {e}")

    async def _close_position(self, reason: str = "signal"):
        """平多仓（市价）"""
        if not self._in_position or self._position_qty <= 0:
            return
        try:
            # 查询实际持仓数量（防止因其他原因数量变化）
            qty = self._position_qty
            try:
                positions = await self.exchange.get_positions()
                for pos in positions:
                    if pos.get("symbol") == self.symbol and float(pos.get("size", 0)) > 0:
                        qty = float(pos["size"])
                        break
            except Exception:
                pass  # 用缓存的 qty

            order = await self.place_order_with_retry(
                side="sell",
                amount=Decimal(str(qty)),
                order_type="market",
            )
            if order:
                # 估算盈亏（avg_price 可能为 0，用最新成交价估算）
                close_price = float(order.get("avgPx") or order.get("avg_price") or
                                    self._entry_price)
                pnl = (close_price - self._entry_price) * qty

                # 更新统计
                self.realized_pnl += pnl
                self.total_trades += 1
                if pnl > 0:
                    self._win_trades += 1
                self.win_rate = self._win_trades / self.total_trades * 100
                self.record_trade_result(pnl)

                logger.info(
                    f"[{self.symbol}] 平多({reason}) qty={qty:.6f} "
                    f"entry={self._entry_price:.2f} close={close_price:.2f} "
                    f"pnl={pnl:+.4f} 累计={self.realized_pnl:+.4f}"
                )

            self._in_position = False
            self._entry_price = 0.0
            self._position_qty = 0.0

        except Exception as e:
            logger.error(f"[{self.symbol}] 平多失败: {e}")
