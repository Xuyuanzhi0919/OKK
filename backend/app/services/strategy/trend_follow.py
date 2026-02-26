"""
趋势跟踪策略 - EMA 双均线交叉（多空双向版）

最优参数（经 256 组网格搜索 + 交叉验证）：
  EMA 快线: 12
  EMA 慢线: 40
  止损:     3.0%（由实时 Ticker 价格触发）
  止盈:     8.0%（由实时 Ticker 价格触发）
  过滤:     RSI14 < 65（开仓前检查，过滤超买）
  方向:     多空双向（SWAP/FUTURES）/ 仅做多（现货）

信号逻辑：
  - 每 15 分钟取一次已确认 K 线的收盘价更新 EMA
  - 金叉（fast 上穿 slow）且 RSI < 65 → 平空（如有）→ 开多
  - 死叉（fast 下穿 slow）→ 平多（如有）→ 开空（仅 SWAP）
  - 实时 Ticker 价格触发止损/止盈（无需等 K 线关闭）

OKX 持仓模式：双向持仓（开平仓模式）
  开多: side="buy",  posSide="long"
  平多: side="sell", posSide="long"
  开空: side="sell", posSide="short"
  平空: side="buy",  posSide="short"
"""
import time
from typing import Dict, List, Optional
from decimal import Decimal
from loguru import logger

from app.services.strategy.base import StrategyBase
from app.services.notification import notification_service
from app.core.database import SessionLocal
from app.models.strategy import Strategy as DBStrategy


# ── 最优超参数（不可随意修改，来自回测验证） ─────────────────────────
_FAST_PERIOD    = 12
_SLOW_PERIOD    = 40
_RSI_PERIOD     = 14
_RSI_THRESHOLD  = 65.0      # RSI 超过此值不开多仓（超买过滤）
_TIMEFRAME      = "15m"
_KLINE_LIMIT    = 80        # 预热 K 线数（>= slow_period + warmup）
_LOOP_SECONDS   = 15 * 60  # 15 分钟换一次 K 线周期


class TrendFollowStrategy(StrategyBase):
    """
    EMA 双均线趋势跟踪策略（多空双向版）

    支持通过 parameters 字典覆盖默认参数：
      - fast_period:    EMA 快线周期（默认 12）
      - slow_period:    EMA 慢线周期（默认 40）
      - stop_loss:      止损比例（默认 0.03 = 3%）
      - take_profit:    止盈比例（默认 0.08 = 8%）
      - position_ratio: 每次开仓占可用资金的比例（默认 0.4 = 40%）
      - use_rsi_filter: 是否启用 RSI 过滤（默认 True，仅过滤开多）
      - rsi_threshold:  RSI 阈值（默认 65.0）
      - trailing_stop:  移动止损回撤比例（默认 0.0 = 禁用）
      - enable_short:   是否启用做空（默认 True，仅 SWAP/FUTURES 有效）
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
        self.stop_loss:     float = float(p.get("stop_loss",    0.03))
        self.take_profit:   float = float(p.get("take_profit",  0.08))
        self.pos_ratio:     float = float(p.get("position_ratio", 0.4))
        self.use_rsi:       bool  = bool(p.get("use_rsi_filter", True))
        self.rsi_threshold: float = float(p.get("rsi_threshold",  _RSI_THRESHOLD))
        self.leverage:      int   = int(p.get("leverage", 10))
        self.trailing_stop: float = float(p.get("trailing_stop", 0.0))
        self.enable_short:  bool  = bool(p.get("enable_short", True))

        # EMA 状态（仅保留最近两个值用于交叉判断）
        self._fast_prev: Optional[float] = None
        self._fast_curr: Optional[float] = None
        self._slow_prev: Optional[float] = None
        self._slow_curr: Optional[float] = None

        # 合约规格（在 start() 时动态获取）
        self._ct_val: float = 0.1
        self._lot_sz: float = 1.0
        self._min_sz: float = 1.0
        self._is_swap: bool = symbol.endswith("-SWAP") or symbol.endswith("-FUTURES")

        # 仓位状态（多空统一管理）
        # _position_side: "" = 无仓, "long" = 多仓, "short" = 空仓
        self._position_side:  str   = ""
        self._entry_price:    float = 0.0
        self._position_qty:   float = 0.0
        self._open_time:      float = 0.0

        # 移动止损（多仓追踪最高价，空仓追踪最低价）
        self._extreme_price:  float = 0.0   # 多仓=最高价, 空仓=最低价
        self._trail_stop_px:  float = 0.0   # 触发价（多仓在下方，空仓在上方）

        # 向后兼容（供 manager 广播和 DB 持久化读取）
        self._highest_price:  float = 0.0   # 等同于 _extreme_price（多仓时）

        # K 线周期追踪
        self._last_kline_period: int = 0

        # 统计数据
        self.realized_pnl:   float = 0.0
        self.total_trades:   int   = 0
        self._win_trades:    int   = 0
        self.win_rate:       float = 0.0
        self._buy_count:     int   = 0
        self._sell_count:    int   = 0
        self._unrealized_pnl: float = 0.0

        logger.info(
            f"TrendFollowStrategy 初始化: {symbol} "
            f"fast={self.fast_period} slow={self.slow_period} "
            f"sl={self.stop_loss*100:.1f}% tp={self.take_profit*100:.1f}% "
            f"做空={'启用' if self.enable_short and self._is_swap else '禁用'}"
        )

    # ── 便捷属性（向后兼容） ──────────────────────────────────────────
    @property
    def _in_position(self) -> bool:
        return self._position_side != ""

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    async def start(self):
        self.is_running = True
        self._last_kline_period = 0

        # ── 从数据库恢复持仓状态（防止重启后持仓信息丢失）────────────
        self._position_side  = ""
        self._entry_price    = 0.0
        self._position_qty   = 0.0
        self._open_time      = 0.0
        self._extreme_price  = 0.0
        self._trail_stop_px  = 0.0

        try:
            _db = SessionLocal()
            try:
                db_s = _db.query(DBStrategy).filter(DBStrategy.id == self.strategy_id).first()
                if db_s and db_s.position_in_position:
                    self._position_side  = getattr(db_s, "position_side", None) or "long"
                    self._entry_price    = float(db_s.position_entry_price or 0)
                    self._position_qty   = float(db_s.position_qty or 0)
                    self._open_time      = float(db_s.position_open_time or 0)
                    self._extreme_price  = float(db_s.position_highest_price or self._entry_price)
                    self._trail_stop_px  = float(db_s.position_trail_stop_px or 0)
                    self._highest_price  = self._extreme_price
                    logger.warning(
                        f"[{self.symbol}] 🔄 重启后恢复持仓: side={self._position_side} "
                        f"qty={self._position_qty} entry={self._entry_price:.2f}"
                    )
            finally:
                _db.close()
        except Exception as e:
            logger.warning(f"[{self.symbol}] 从数据库恢复持仓状态失败，视为无持仓: {e}")

        # 获取合约规格
        if self._is_swap:
            try:
                inst_type = "SWAP" if self.symbol.endswith("-SWAP") else "FUTURES"
                instruments = await self.exchange.get_instruments(
                    inst_type=inst_type, inst_id=self.symbol
                )
                if instruments:
                    info = instruments[0]
                    self._ct_val = float(info.get("ctVal", self._ct_val))
                    self._lot_sz = float(info.get("lotSz", self._lot_sz))
                    self._min_sz = float(info.get("minSz", self._min_sz))
                    logger.info(
                        f"[{self.symbol}] 合约规格: ctVal={self._ct_val} "
                        f"lotSz={self._lot_sz} minSz={self._min_sz}"
                    )
            except Exception as e:
                logger.warning(f"[{self.symbol}] 获取合约规格失败，使用默认值: {e}")

            # 设置杠杆（双向持仓模式需分别设置 long/short）
            try:
                margin_mode = self.parameters.get("margin_mode", "isolated")
                for side in ("long", "short"):
                    try:
                        await self.exchange.set_leverage(
                            lever=str(self.leverage),
                            mgn_mode=margin_mode,
                            inst_id=self.symbol,
                            pos_side=side,
                        )
                    except Exception:
                        pass  # 若账户是买卖模式则单独设置
                # 兜底：买卖模式下不带 pos_side
                await self.exchange.set_leverage(
                    lever=str(self.leverage),
                    mgn_mode=margin_mode,
                    inst_id=self.symbol,
                )
                logger.info(f"[{self.symbol}] 杠杆已设置为 {self.leverage}x ({margin_mode})")
            except Exception as e:
                logger.warning(f"[{self.symbol}] 设置杠杆失败: {e}")

        # 用历史 K 线预热 EMA
        await self._init_ema()

        # 立即入场：处于上升趋势且无持仓 → 开多
        if (self._fast_curr is not None and
                self._slow_curr is not None and
                self._fast_curr > self._slow_curr and
                self._position_side == ""):
            try:
                ticker = await self.exchange.get_ticker(self.symbol)
                price = float(ticker.get("last", 0))
                if price > 0:
                    klines = await self.exchange.get_kline(self.symbol, _TIMEFRAME, _KLINE_LIMIT)
                    confirmed = [k for k in reversed(klines) if k.get("confirm") == "1"]
                    closes = [float(k["c"]) for k in confirmed]
                    if self.use_rsi and closes and self._rsi(closes) >= self.rsi_threshold:
                        logger.info(
                            f"[{self.symbol}] 启动时处于上升趋势但 RSI 超买({self._rsi(closes):.1f})，等待金叉"
                        )
                    else:
                        logger.info(
                            f"[{self.symbol}] 启动时处于上升趋势，立即开多"
                        )
                        await self._open_long_position(price)
            except Exception as e:
                logger.warning(f"[{self.symbol}] 启动时立即入场失败: {e}")

        now_ms = int(time.time() * 1000)
        period_ms = 15 * 60 * 1000
        self._last_kline_period = (now_ms // period_ms) * period_ms

        logger.info(f"策略 {self.strategy_id} [{self.symbol}] 已启动")

    async def stop(self, cancel_orders: bool = True, close_position: bool = True):
        self.is_running = False
        if close_position:
            if self._position_side == "long":
                await self._close_long_position(reason="stop")
            elif self._position_side == "short":
                await self._close_short_position(reason="stop")
        logger.info(f"策略 {self.strategy_id} [{self.symbol}] 已停止 (平仓={close_position})")

    # ═══════════════════════════════════════════════════════════
    # 核心 Tick 回调
    # ═══════════════════════════════════════════════════════════

    async def on_tick(self, ticker: Dict):
        if not self.is_running:
            return

        price = float(ticker.get("last", 0))
        if price <= 0:
            return

        # ── 更新未实现盈亏 ────────────────────────────────────────────
        if self._position_side and self._entry_price > 0 and self._position_qty > 0:
            ct_val = self._ct_val if self._is_swap else 1.0
            if self._position_side == "long":
                self._unrealized_pnl = (price - self._entry_price) * self._position_qty * ct_val
            else:
                self._unrealized_pnl = (self._entry_price - price) * self._position_qty * ct_val
        else:
            self._unrealized_pnl = 0.0

        # ── 止损 / 止盈（实时触发）───────────────────────────────────
        if self._position_side and self._entry_price > 0:
            if self._position_side == "long":
                pnl_pct = (price - self._entry_price) / self._entry_price
            else:
                pnl_pct = (self._entry_price - price) / self._entry_price

            # 移动止损
            if self.trailing_stop > 0:
                if self._position_side == "long":
                    if price > self._extreme_price:
                        self._extreme_price = price
                        self._highest_price = price
                        self._trail_stop_px = price * (1 - self.trailing_stop)
                        logger.debug(
                            f"[{self.symbol}] 多仓移动止损上移: 最高={self._extreme_price:.2f}"
                            f" 止损价={self._trail_stop_px:.2f}"
                        )
                    if price <= self._trail_stop_px:
                        logger.info(
                            f"[{self.symbol}] 多仓触发移动止损 price={price:.2f}"
                            f" 止损价={self._trail_stop_px:.2f} pnl={pnl_pct*100:.2f}%"
                        )
                        await self._close_long_position(reason="trailing_stop")
                        return
                else:  # short
                    if price < self._extreme_price or self._extreme_price == 0:
                        self._extreme_price = price
                        self._trail_stop_px = price * (1 + self.trailing_stop)
                        logger.debug(
                            f"[{self.symbol}] 空仓移动止损下移: 最低={self._extreme_price:.2f}"
                            f" 止损价={self._trail_stop_px:.2f}"
                        )
                    if price >= self._trail_stop_px:
                        logger.info(
                            f"[{self.symbol}] 空仓触发移动止损 price={price:.2f}"
                            f" 止损价={self._trail_stop_px:.2f} pnl={pnl_pct*100:.2f}%"
                        )
                        await self._close_short_position(reason="trailing_stop")
                        return
            else:
                # 固定止损
                if pnl_pct <= -self.stop_loss:
                    logger.info(f"[{self.symbol}] 触发止损 {pnl_pct*100:.2f}% ({self._position_side})")
                    if self._position_side == "long":
                        await self._close_long_position(reason="stop_loss")
                    else:
                        await self._close_short_position(reason="stop_loss")
                    return

            # 止盈
            if pnl_pct >= self.take_profit:
                logger.info(f"[{self.symbol}] 触发止盈 {pnl_pct*100:.2f}% ({self._position_side})")
                if self._position_side == "long":
                    await self._close_long_position(reason="take_profit")
                else:
                    await self._close_short_position(reason="take_profit")
                return

        # ── 15 分钟 K 线信号 ──────────────────────────────────────────
        now_ms = int(time.time() * 1000)
        period_ms = 15 * 60 * 1000
        current_period = (now_ms // period_ms) * period_ms

        if current_period != self._last_kline_period:
            self._last_kline_period = current_period
            await self._process_kline_signal()

    async def calculate_pnl(self) -> Dict:
        unrealized = self._unrealized_pnl
        try:
            if self._position_side and self._entry_price > 0 and self._position_qty > 0:
                ticker = await self.exchange.get_ticker(self.symbol)
                current_price = float(ticker.get("last", 0))
                if current_price > 0:
                    ct_val = self._ct_val if self._is_swap else 1.0
                    if self._position_side == "long":
                        unrealized = (current_price - self._entry_price) * self._position_qty * ct_val
                    else:
                        unrealized = (self._entry_price - current_price) * self._position_qty * ct_val
        except Exception as e:
            logger.warning(f"[{self.symbol}] 计算未实现盈亏失败: {e}")

        return {
            "total_pnl":      round(self.realized_pnl + unrealized, 4),
            "realized_pnl":   round(self.realized_pnl, 4),
            "unrealized_pnl": round(unrealized, 4),
            "total_fee":      0,
            "pnl_rate":       0,
            "buy_count":      self._buy_count,
            "sell_count":     self._sell_count,
            "win_rate":       round(self.win_rate, 1),
            "in_position":    self._in_position,
            "position_side":  self._position_side,
            "entry_price":    self._entry_price,
        }

    async def on_kline(self, kline: Dict):
        pass

    async def on_order_update(self, order: Dict):
        logger.debug(f"[{self.symbol}] 订单更新: {order.get('order_id')} status={order.get('status')}")

    # ═══════════════════════════════════════════════════════════
    # K 线信号
    # ═══════════════════════════════════════════════════════════

    async def _process_kline_signal(self):
        try:
            klines = await self.exchange.get_kline(self.symbol, _TIMEFRAME, _KLINE_LIMIT)
        except Exception as e:
            logger.error(f"[{self.symbol}] 获取 K 线失败: {e}")
            return

        if not klines or len(klines) < self.slow_period + 2:
            return

        confirmed = [k for k in reversed(klines) if k.get("confirm") == "1"]
        if len(confirmed) < self.slow_period + 2:
            return

        closes = [float(k["c"]) for k in confirmed]
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

        current_price = float(klines[0]["c"])

        logger.debug(
            f"[{self.symbol}] EMA fast={self._fast_curr:.4f} slow={self._slow_curr:.4f} "
            f"golden={golden} death={death} pos={self._position_side or '无'}"
        )

        if golden:
            # 金叉：先平空仓，再开多仓
            if self._position_side == "short":
                logger.info(f"[{self.symbol}] 金叉，平空仓后开多")
                await self._close_short_position(reason="golden_cross")

            if self._position_side == "":
                if self.use_rsi and self._rsi(closes) >= self.rsi_threshold:
                    logger.info(f"[{self.symbol}] 金叉但 RSI 超买({self._rsi(closes):.1f})，跳过开多")
                    return
                await self._open_long_position(current_price)

        elif death:
            # 死叉：先平多仓（有最短持仓保护），再开空仓
            if self._position_side == "long":
                min_hold_sec = 15 * 60
                held_sec = time.time() - self._open_time
                if held_sec < min_hold_sec:
                    logger.info(
                        f"[{self.symbol}] 死叉，但多仓持仓时间仅 {held_sec:.0f}s < {min_hold_sec}s，跳过"
                    )
                    return
                logger.info(f"[{self.symbol}] 死叉，平多仓后开空")
                await self._close_long_position(reason="death_cross")

            if self._position_side == "" and self._is_swap and self.enable_short:
                await self._open_short_position(current_price)

    # ═══════════════════════════════════════════════════════════
    # EMA 计算
    # ═══════════════════════════════════════════════════════════

    def _update_ema_from_closes(self, closes: List[float]):
        if len(closes) < self.slow_period:
            return

        fast_k = 2 / (self.fast_period + 1)
        slow_k = 2 / (self.slow_period + 1)

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
        try:
            klines = await self.exchange.get_kline(self.symbol, _TIMEFRAME, _KLINE_LIMIT)
            if klines and len(klines) >= self.slow_period + 2:
                confirmed = [k for k in reversed(klines) if k.get("confirm") == "1"]
                closes = [float(k["c"]) for k in confirmed]
                self._update_ema_from_closes(closes)
                if self._fast_curr and self._slow_curr:
                    logger.info(
                        f"[{self.symbol}] EMA 预热完成: fast={self._fast_curr:.2f} slow={self._slow_curr:.2f}"
                    )
        except Exception as e:
            logger.warning(f"[{self.symbol}] EMA 预热失败: {e}")

    @staticmethod
    def _rsi(closes: List[float], period: int = _RSI_PERIOD) -> float:
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
    # 开平仓（四个方向独立实现）
    # ═══════════════════════════════════════════════════════════

    async def _calc_qty(self, price: float) -> float:
        """根据可用余额和 pos_ratio 计算下单数量"""
        balance = await self.exchange.get_balance()
        available = 0.0
        for d in balance.get("details", []):
            if d.get("ccy") == "USDT":
                available = float(d.get("availBal", 0))
                break

        if available <= 10:
            logger.warning(f"[{self.symbol}] 可用 USDT 余额不足({available:.2f})")
            return 0.0

        margin_budget = available * self.pos_ratio

        if self._is_swap:
            notional = margin_budget * self.leverage
            contracts = notional / (price * self._ct_val) if self._ct_val > 0 else 1
            qty = max(self._min_sz, int(contracts / self._lot_sz) * self._lot_sz)
        else:
            qty = round(margin_budget / price, 6)

        return qty

    async def _open_long_position(self, price: float):
        """开多仓（market buy, posSide=long）"""
        if self._position_side != "":
            return
        try:
            qty = await self._calc_qty(price)
            if qty <= 0:
                return

            margin_budget = 0.0
            balance = await self.exchange.get_balance()
            for d in balance.get("details", []):
                if d.get("ccy") == "USDT":
                    margin_budget = float(d.get("availBal", 0)) * self.pos_ratio
                    break

            logger.info(
                f"[{self.symbol}] 准备开多: qty={qty} 保证金={margin_budget:.2f} USDT @ {price:.2f}"
            )

            order = await self.place_order_with_retry(
                side="buy",
                amount=Decimal(str(qty)),
                order_type="market",
                pos_side="long",
            )
            if order:
                self._position_side = "long"
                self._open_time     = time.time()
                avg_px = order.get("avgPx") or order.get("fillPx")
                self._entry_price   = float(avg_px) if avg_px and float(avg_px) > 0 else price
                self._position_qty  = qty
                self._extreme_price = self._entry_price
                self._highest_price = self._entry_price
                self._buy_count    += 1
                if self.trailing_stop > 0:
                    self._trail_stop_px = self._entry_price * (1 - self.trailing_stop)
                else:
                    self._trail_stop_px = 0.0
                logger.info(
                    f"[{self.symbol}] 开多成功 qty={qty} entry={self._entry_price:.2f}"
                )
                await self._notify_open("long", qty, margin_budget)
        except Exception as e:
            logger.error(f"[{self.symbol}] 开多失败: {e}")

    async def _close_long_position(self, reason: str = "signal"):
        """平多仓（market sell, posSide=long）"""
        if self._position_side != "long" or self._position_qty <= 0:
            return

        saved_entry = self._entry_price
        saved_qty   = self._position_qty
        self._position_side  = ""
        self._entry_price    = 0.0
        self._position_qty   = 0.0

        try:
            qty = saved_qty
            try:
                positions = await self.exchange.get_positions()
                for pos in positions:
                    if (pos.get("symbol") == self.symbol and
                            pos.get("posSide", "net") in ("long", "net") and
                            float(pos.get("size", 0)) > 0):
                        qty = float(pos["size"])
                        break
            except Exception:
                pass

            order = await self.place_order_with_retry(
                side="sell",
                amount=Decimal(str(qty)),
                order_type="market",
                pos_side="long",
            )
            if order:
                close_price = float(order.get("avgPx") or order.get("fillPx") or saved_entry)
                ct_val = self._ct_val if self._is_swap else 1.0
                pnl = (close_price - saved_entry) * qty * ct_val
                self._sell_count += 1
                self._update_stats(pnl)
                logger.info(
                    f"[{self.symbol}] 平多({reason}) qty={qty} "
                    f"entry={saved_entry:.2f} close={close_price:.2f} pnl={pnl:+.4f}"
                )
                await self._notify_close("long", saved_entry, close_price, qty, pnl, reason)
            else:
                self._position_side = "long"
                self._entry_price   = saved_entry
                self._position_qty  = saved_qty
        except Exception as e:
            logger.error(f"[{self.symbol}] 平多失败: {e}")
            self._position_side = "long"
            self._entry_price   = saved_entry
            self._position_qty  = saved_qty

    async def _open_short_position(self, price: float):
        """开空仓（market sell, posSide=short）— 仅 SWAP/FUTURES"""
        if not self._is_swap or not self.enable_short:
            return
        if self._position_side != "":
            return
        try:
            qty = await self._calc_qty(price)
            if qty <= 0:
                return

            margin_budget = 0.0
            balance = await self.exchange.get_balance()
            for d in balance.get("details", []):
                if d.get("ccy") == "USDT":
                    margin_budget = float(d.get("availBal", 0)) * self.pos_ratio
                    break

            logger.info(
                f"[{self.symbol}] 准备开空: qty={qty} 保证金={margin_budget:.2f} USDT @ {price:.2f}"
            )

            order = await self.place_order_with_retry(
                side="sell",
                amount=Decimal(str(qty)),
                order_type="market",
                pos_side="short",
            )
            if order:
                self._position_side = "short"
                self._open_time     = time.time()
                avg_px = order.get("avgPx") or order.get("fillPx")
                self._entry_price   = float(avg_px) if avg_px and float(avg_px) > 0 else price
                self._position_qty  = qty
                self._extreme_price = self._entry_price
                self._sell_count   += 1
                if self.trailing_stop > 0:
                    self._trail_stop_px = self._entry_price * (1 + self.trailing_stop)
                else:
                    self._trail_stop_px = 0.0
                logger.info(
                    f"[{self.symbol}] 开空成功 qty={qty} entry={self._entry_price:.2f}"
                )
                await self._notify_open("short", qty, margin_budget)
        except Exception as e:
            logger.error(f"[{self.symbol}] 开空失败: {e}")

    async def _close_short_position(self, reason: str = "signal"):
        """平空仓（market buy, posSide=short）"""
        if self._position_side != "short" or self._position_qty <= 0:
            return

        saved_entry = self._entry_price
        saved_qty   = self._position_qty
        self._position_side  = ""
        self._entry_price    = 0.0
        self._position_qty   = 0.0

        try:
            qty = saved_qty
            try:
                positions = await self.exchange.get_positions()
                for pos in positions:
                    if (pos.get("symbol") == self.symbol and
                            pos.get("posSide", "") == "short" and
                            float(pos.get("size", 0)) > 0):
                        qty = float(pos["size"])
                        break
            except Exception:
                pass

            order = await self.place_order_with_retry(
                side="buy",
                amount=Decimal(str(qty)),
                order_type="market",
                pos_side="short",
            )
            if order:
                close_price = float(order.get("avgPx") or order.get("fillPx") or saved_entry)
                ct_val = self._ct_val if self._is_swap else 1.0
                pnl = (saved_entry - close_price) * qty * ct_val
                self._buy_count += 1
                self._update_stats(pnl)
                logger.info(
                    f"[{self.symbol}] 平空({reason}) qty={qty} "
                    f"entry={saved_entry:.2f} close={close_price:.2f} pnl={pnl:+.4f}"
                )
                await self._notify_close("short", saved_entry, close_price, qty, pnl, reason)
            else:
                self._position_side = "short"
                self._entry_price   = saved_entry
                self._position_qty  = saved_qty
        except Exception as e:
            logger.error(f"[{self.symbol}] 平空失败: {e}")
            self._position_side = "short"
            self._entry_price   = saved_entry
            self._position_qty  = saved_qty

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    def _update_stats(self, pnl: float):
        self.realized_pnl += pnl
        self.total_trades += 1
        if pnl > 0:
            self._win_trades += 1
        self.win_rate = self._win_trades / self.total_trades * 100
        self.record_trade_result(pnl)

    async def _notify_open(self, side: str, qty: float, margin: float):
        try:
            await notification_service.notify_position_opened(
                user_id=self.user_id,
                strategy_id=self.strategy_id,
                strategy_name=f"趋势策略#{self.strategy_id}",
                symbol=self.symbol,
                side=side,
                entry_price=self._entry_price,
                amount=qty,
                leverage=self.leverage,
                margin=margin,
            )
        except Exception as e:
            logger.warning(f"[{self.symbol}] 开仓通知失败: {e}")

    async def _notify_close(
        self, side: str, entry: float, close: float, qty: float, pnl: float, reason: str
    ):
        reason_map = {
            "stop_loss":     "止损平仓",
            "trailing_stop": "移动止损",
            "take_profit":   "止盈平仓",
            "death_cross":   "死叉平多",
            "golden_cross":  "金叉平空",
            "stop":          "手动停止",
        }
        pnl_pct = (close - entry) / entry * 100 if entry > 0 else 0
        if side == "short":
            pnl_pct = -pnl_pct
        try:
            await notification_service.notify_position_closed(
                user_id=self.user_id,
                strategy_id=self.strategy_id,
                strategy_name=f"趋势策略#{self.strategy_id}",
                symbol=self.symbol,
                side=side,
                entry_price=entry,
                exit_price=close,
                amount=qty,
                pnl=pnl,
                pnl_pct=pnl_pct,
                reason=reason_map.get(reason, reason),
            )
        except Exception as e:
            logger.warning(f"[{self.symbol}] 平仓通知失败: {e}")
