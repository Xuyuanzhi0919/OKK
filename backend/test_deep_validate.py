"""
多维度深度验证脚本

维度1：多品种 × 多时间周期矩阵（推荐配置打全表）
维度2：滚动窗口回测 Walk-Forward（15m 拆 3 段）
维度3：参数敏感性分析（逐一扰动单参数）
维度4：风险指标汇总（Sharpe / 最大回撤 / Calmar / Profit Factor）
维度5：多空对比（Long-only vs Long+Short）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math
import logging
from typing import List, Dict, Optional
from loguru import logger
from app.core.database import SessionLocal
from app.services.backtest.backtest_engine import BacktestEngine
from app.models import Kline
from sqlalchemy import and_

# ── 静音日志 ──────────────────────────────────────────────────
logging.disable(logging.CRITICAL)
logger.remove()
logger.add(sys.stderr, level="ERROR")

# ── 推荐最优配置 ───────────────────────────────────────────────
BEST_FAST   = 12
BEST_SLOW   = 40
BEST_SL     = 0.01
BEST_TP     = 0.08
USE_RSI     = True        # 结论：仅 RSI 过滤最优
RSI_THRESH  = 65.0
CAPITAL     = 10_000.0
POS_RATIO   = 0.4

SYMBOLS     = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
INTERVALS   = ["15m", "1H", "4H"]


# ═══════════════════════════════════════════════════════════════
# 引擎（支持做空）
# ═══════════════════════════════════════════════════════════════

class TrendFollowEngineV3(BacktestEngine):
    """EMA 双均线策略（支持过滤条件 + 可选做空）"""

    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        fast_period: int = 12,
        slow_period: int = 40,
        amount_per_trade: float = 0.01,
        fee_rate: float = 0.0005,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.08,
        use_rsi_filter: bool = False,
        rsi_threshold: float = 65.0,
        use_trend_filter: bool = False,
        use_volume_filter: bool = False,
        enable_short: bool = False,
    ):
        super().__init__(
            symbol=symbol,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            leverage=1,
            enable_short=enable_short,
        )
        self.fast_period  = fast_period
        self.slow_period  = slow_period
        self.amount       = amount_per_trade
        self.sl           = stop_loss_pct
        self.tp           = take_profit_pct
        self.use_rsi      = use_rsi_filter
        self.rsi_thr      = rsi_threshold
        self.use_trend    = use_trend_filter
        self.use_vol      = use_volume_filter
        self._enable_short = enable_short

        self.prices: List[float] = []
        self.volumes: List[float] = []
        self.fast_h: List[float] = []
        self.slow_h: List[float] = []
        self.trend_h: List[float] = []
        self.entry_price = 0.0

        # 净值曲线（每根 K 线记录一次，用于 Sharpe 计算）
        self.equity_series: List[float] = []
        self._peak = initial_capital
        self.max_dd = 0.0

    def reset(self):
        super().reset()
        self.prices, self.volumes = [], []
        self.fast_h, self.slow_h, self.trend_h = [], [], []
        self.entry_price = 0.0
        self.equity_series = []
        self._peak = self.initial_capital
        self.max_dd = 0.0

    # ── 指标 ────────────────────────────────────────────────
    @staticmethod
    def _ema(prev, price, period, prices):
        k = 2 / (period + 1)
        if prev is None:
            if len(prices) < period:
                return sum(prices) / len(prices)
            return sum(prices[-period:]) / period
        return (price - prev) * k + prev

    @staticmethod
    def _rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(-period, 0):
            d = prices[i] - prices[i - 1]
            (gains if d > 0 else losses).append(abs(d))
        ag = sum(gains) / period
        al = sum(losses) / period
        return 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)

    @staticmethod
    def _vol_ma(vols: List[float], period: int = 10) -> float:
        if len(vols) < period:
            return vols[-1] if vols else 0
        return sum(vols[-period:]) / period

    def _equity(self, price: float) -> float:
        eq = self.capital
        if self.position.amount > 0:
            eq += (price - self.position.avg_price) * self.position.amount
        elif self.position.amount < 0:
            eq += (self.position.avg_price - price) * abs(self.position.amount)
        return eq

    def _update_dd(self, price: float):
        eq = self._equity(price)
        self.equity_series.append(eq)
        if eq > self._peak:
            self._peak = eq
        dd = (self._peak - eq) / self._peak * 100
        if dd > self.max_dd:
            self.max_dd = dd

    # ── 主逻辑 ───────────────────────────────────────────────
    def on_kline(self, kline: Dict):
        ts    = int(kline['timestamp'])
        close = float(kline['close'])
        vol   = float(kline['volume'])

        self.prices.append(close)
        self.volumes.append(vol)
        self.current_kline = kline

        pf = self.fast_h[-1] if self.fast_h else None
        ps = self.slow_h[-1] if self.slow_h else None
        pt = self.trend_h[-1] if self.trend_h else None

        fe = self._ema(pf, close, self.fast_period, self.prices)
        se = self._ema(ps, close, self.slow_period, self.prices)
        te = self._ema(pt, close, 100, self.prices)

        self.fast_h.append(fe)
        self.slow_h.append(se)
        self.trend_h.append(te)
        self._update_dd(close)

        if len(self.prices) < self.slow_period + 2:
            return

        pfe = self.fast_h[-2]
        pse = self.slow_h[-2]

        # ── 止损 / 止盈 ──────────────────────────────────────
        has_long  = self.position.amount > 0
        has_short = self.position.amount < 0

        if has_long and self.entry_price > 0:
            pnl_pct = (close - self.entry_price) / self.entry_price
            if pnl_pct <= -self.sl or pnl_pct >= self.tp:
                self.sell(close, self.position.amount, ts)
                self.entry_price = 0.0
                return

        if has_short and self.entry_price > 0:
            pnl_pct = (self.entry_price - close) / self.entry_price
            if pnl_pct <= -self.sl or pnl_pct >= self.tp:
                self.cover(close, abs(self.position.amount), ts)
                self.entry_price = 0.0
                return

        # ── 均线信号 ──────────────────────────────────────────
        golden = (pfe <= pse) and (fe > se)
        death  = (pfe >= pse) and (fe < se)

        # 过滤条件（只用于开多）
        rsi_ok  = (not self.use_rsi)  or (self._rsi(self.prices) < self.rsi_thr)
        trd_ok  = (not self.use_trend) or (close > te)
        vol_ok  = (not self.use_vol)  or (vol >= self._vol_ma(self.volumes))

        # 开多
        if golden and not has_long and (not has_short):
            if rsi_ok and trd_ok and vol_ok:
                t = self.buy(close, self.amount, ts)
                if t:
                    self.entry_price = close

        # 平多 → 并可能开空
        elif death and has_long:
            self.sell(close, self.position.amount, ts)
            self.entry_price = 0.0
            if self._enable_short:
                t = self.short(close, self.amount, ts)
                if t:
                    self.entry_price = close

        # 纯做空入场（空仓 + death cross + enable_short）
        elif death and not has_long and not has_short and self._enable_short:
            t = self.short(close, self.amount, ts)
            if t:
                self.entry_price = close

        # 平空 → 可能开多
        elif golden and has_short:
            self.cover(close, abs(self.position.amount), ts)
            self.entry_price = 0.0
            if rsi_ok and trd_ok and vol_ok:
                t = self.buy(close, self.amount, ts)
                if t:
                    self.entry_price = close


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def load_klines(symbol: str, interval: str,
                days: int = 30, offset_days: int = 0) -> List:
    """从数据库加载 K 线（最新 days 天，可向前偏移 offset_days 天）"""
    from datetime import datetime, timedelta, timezone
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ts = now_ts - offset_days * 86_400_000
    start_ts = end_ts - days * 86_400_000

    with SessionLocal() as db:
        rows = (
            db.query(Kline)
            .filter(
                and_(
                    Kline.symbol == symbol,
                    Kline.interval == interval,
                    Kline.timestamp >= start_ts,
                    Kline.timestamp < end_ts,
                )
            )
            .order_by(Kline.timestamp.asc())
            .all()
        )
    return rows


def run_bt(klines: list,
           fast: int = BEST_FAST,
           slow: int = BEST_SLOW,
           sl: float = BEST_SL,
           tp: float = BEST_TP,
           use_rsi: bool = USE_RSI,
           use_trend: bool = False,
           use_vol: bool = False,
           enable_short: bool = False,
           capital: float = CAPITAL,
           pos_ratio: float = POS_RATIO) -> Optional[Dict]:
    """运行单次回测，返回指标字典"""
    if not klines or len(klines) < slow + 5:
        return None

    first_price = float(klines[0].open)
    last_price  = float(klines[-1].close)
    amt = capital * pos_ratio / first_price

    eng = TrendFollowEngineV3(
        symbol="",
        initial_capital=capital,
        fast_period=fast,
        slow_period=slow,
        amount_per_trade=amt,
        fee_rate=0.0005,
        stop_loss_pct=sl,
        take_profit_pct=tp,
        use_rsi_filter=use_rsi,
        rsi_threshold=RSI_THRESH,
        use_trend_filter=use_trend,
        use_volume_filter=use_vol,
        enable_short=enable_short,
    )

    for k in klines:
        eng.on_kline({
            'timestamp': k.timestamp,
            'open': k.open, 'high': k.high,
            'low': k.low,   'close': k.close,
            'volume': k.volume,
        })

    # 最终净值（含未平仓估值）
    final = capital
    if eng.position.amount > 0:
        final = eng.capital + (last_price - eng.position.avg_price) * eng.position.amount
    elif eng.position.amount < 0:
        final = eng.capital + (eng.position.avg_price - last_price) * abs(eng.position.amount)
    else:
        final = eng.capital

    closed = [t for t in eng.trades if t.side in ('sell', 'cover')]
    wins   = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]

    win_rate = len(wins) / len(closed) * 100 if closed else 0.0
    tw = sum(t.pnl for t in wins)
    tl = abs(sum(t.pnl for t in losses))
    pf = tw / tl if tl > 0 else (99.0 if tw > 0 else 0.0)
    total_ret = (final - capital) / capital * 100

    # Sharpe（基于净值序列日收益）
    sharpe = _sharpe(eng.equity_series, interval_str=None)

    # Calmar = 年化收益 / 最大回撤
    days_cnt = len(klines) * _bar_minutes(None) / 1440  # 粗估天数（用 K 线数量）
    ann_ret = total_ret * (365 / max(days_cnt, 1))
    calmar = ann_ret / eng.max_dd if eng.max_dd > 0 else 99.0

    return {
        'return':    round(total_ret, 2),
        'win_rate':  round(win_rate, 1),
        'trades':    len(closed),
        'pf':        round(pf, 2),
        'max_dd':    round(eng.max_dd, 2),
        'sharpe':    round(sharpe, 2),
        'calmar':    round(calmar, 2),
    }


def _bar_minutes(interval: Optional[str]) -> int:
    """K 线周期 → 分钟数（用于 Sharpe 年化）"""
    if interval is None:
        return 15
    m = {'1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
         '1H': 60, '2H': 120, '4H': 240, '1D': 1440}
    return m.get(interval, 15)


def _sharpe(equity: List[float], interval_str: Optional[str]) -> float:
    """年化 Sharpe（基于净值序列）"""
    if len(equity) < 10:
        return 0.0
    rets = [(equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity))]
    n = len(rets)
    if n < 2:
        return 0.0
    mean_r = sum(rets) / n
    std_r  = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / (n - 1))
    if std_r == 0:
        return 0.0
    bars_per_year = 365 * 24 * 60 / _bar_minutes(interval_str)
    return mean_r / std_r * math.sqrt(bars_per_year)


def sep(ch='─', w=92):
    print(ch * w)


# ═══════════════════════════════════════════════════════════════
# 维度 1：多品种 × 多时间周期矩阵
# ═══════════════════════════════════════════════════════════════

def dim1_matrix():
    print()
    sep('═')
    print("维度 1：多品种 × 多时间周期矩阵  [推荐配置: fast=12 slow=40 sl=1% tp=8% RSI过滤]")
    sep('═')
    hdr = f"{'品种':20s} {'周期':5s} {'K线数':>6} {'收益%':>8} {'胜率%':>7} {'交易数':>6} {'PF':>6} {'最大DD%':>8} {'Sharpe':>8} {'Calmar':>8}"
    print(hdr)
    sep()

    for sym in SYMBOLS:
        for itv in INTERVALS:
            klines = load_klines(sym, itv, days=21)
            if not klines:
                print(f"{sym:20s} {itv:5s}  {'无数据':>6}")
                continue
            r = run_bt(klines)
            if r is None:
                print(f"{sym:20s} {itv:5s}  {'数据不足':>6}")
                continue
            print(f"{sym:20s} {itv:5s} {len(klines):6d} "
                  f"{r['return']:>+8.2f}% "
                  f"{r['win_rate']:>6.1f}% "
                  f"{r['trades']:>6d} "
                  f"{r['pf']:>6.2f} "
                  f"{r['max_dd']:>7.2f}% "
                  f"{r['sharpe']:>8.2f} "
                  f"{r['calmar']:>8.2f}")
    sep()


# ═══════════════════════════════════════════════════════════════
# 维度 2：滚动窗口 Walk-Forward（BTC+ETH 15m，拆 3 段）
# ═══════════════════════════════════════════════════════════════

def dim2_walk_forward():
    print()
    sep('═')
    print("维度 2：Walk-Forward 滚动窗口（15m 数据拆 3 段，验证时间稳定性）")
    sep('═')
    hdr = f"{'品种':20s} {'窗口':8s} {'K线范围':>14} {'收益%':>8} {'胜率%':>7} {'交易数':>6} {'PF':>6} {'最大DD%':>8}"
    print(hdr)
    sep()

    for sym in SYMBOLS:
        klines = load_klines(sym, "15m", days=21)
        if len(klines) < 90:
            print(f"{sym}: 数据不足")
            continue

        n = len(klines)
        w = n // 3
        windows = [(0, w), (w, 2 * w), (2 * w, n)]
        labels = ["窗口1(早期)", "窗口2(中期)", "窗口3(近期)"]

        for (a, b), label in zip(windows, labels):
            seg = klines[a:b]
            r = run_bt(seg)
            if r is None:
                print(f"{sym:20s} {label:10s} [{a:4d}~{b:4d}]  数据不足")
                continue
            print(f"{sym:20s} {label:10s} [{a:4d}~{b:4d}]"
                  f" {r['return']:>+8.2f}%"
                  f" {r['win_rate']:>6.1f}%"
                  f" {r['trades']:>6d}"
                  f" {r['pf']:>6.2f}"
                  f" {r['max_dd']:>7.2f}%")
    sep()


# ═══════════════════════════════════════════════════════════════
# 维度 3：参数敏感性分析（逐一扰动单参数，BTC 15m）
# ═══════════════════════════════════════════════════════════════

def dim3_sensitivity():
    print()
    sep('═')
    print("维度 3：参数敏感性分析（每次只变动一个参数，BTC 15m，其余保持最优值）")
    sep('═')

    klines = load_klines("BTC-USDT-SWAP", "15m", days=21)
    if not klines:
        print("BTC 15m 数据不足")
        return

    base_r = run_bt(klines)
    print(f"  基准配置 (fast={BEST_FAST} slow={BEST_SLOW} sl={BEST_SL*100:.1f}% tp={BEST_TP*100:.1f}% RSI过滤): "
          f"收益 {base_r['return']:+.2f}%  胜率 {base_r['win_rate']:.1f}%  "
          f"交易数 {base_r['trades']}  PF {base_r['pf']:.2f}  MaxDD {base_r['max_dd']:.2f}%")
    print()

    def scan(label, param, values, kw_key):
        print(f"  ── {label} ──")
        hdr = f"  {'参数值':>10} {'收益%':>8} {'胜率%':>7} {'交易数':>6} {'PF':>6} {'MaxDD%':>8} {'Sharpe':>8}"
        print(hdr)
        for v in values:
            kw = dict(fast=BEST_FAST, slow=BEST_SLOW, sl=BEST_SL,
                      tp=BEST_TP, use_rsi=USE_RSI)
            kw[kw_key] = v
            r = run_bt(klines, **kw)
            if r is None:
                print(f"  {v:>10}  数据不足")
                continue
            marker = " ◀" if v == getattr({'fast': BEST_FAST, 'slow': BEST_SLOW,
                                           'sl': BEST_SL, 'tp': BEST_TP}
                                          .get(kw_key, v), kw_key, None) else ""
            print(f"  {str(v):>10} {r['return']:>+8.2f}% {r['win_rate']:>6.1f}%"
                  f" {r['trades']:>6d} {r['pf']:>6.2f} {r['max_dd']:>7.2f}%"
                  f" {r['sharpe']:>8.2f}{marker}")
        print()

    scan("fast_period（快线）", "fast_period",
         [5, 7, 9, 12, 15, 20], "fast")
    scan("slow_period（慢线）", "slow_period",
         [20, 25, 30, 40, 55, 70], "slow")
    scan("stop_loss（止损%）", "stop_loss",
         [0.005, 0.01, 0.015, 0.02, 0.03, 0.05], "sl")
    scan("take_profit（止盈%）", "take_profit",
         [0.03, 0.05, 0.08, 0.10, 0.15, 0.20], "tp")
    sep()


# ═══════════════════════════════════════════════════════════════
# 维度 4：风险指标详细对比（有无 RSI 过滤 × BTC/ETH × 15m）
# ═══════════════════════════════════════════════════════════════

def dim4_risk_metrics():
    print()
    sep('═')
    print("维度 4：风险指标详细对比（无过滤 vs RSI过滤，BTC+ETH 15m）")
    sep('═')
    hdr = f"{'品种':20s} {'过滤':8s} {'收益%':>8} {'胜率%':>7} {'交易数':>6} {'PF':>6} {'MaxDD%':>8} {'Sharpe':>8} {'Calmar':>8}"
    print(hdr)
    sep()

    for sym in SYMBOLS:
        klines = load_klines(sym, "15m", days=21)
        if not klines:
            continue
        for use_rsi, label in [(False, "无过滤"), (True, "RSI<65")]:
            r = run_bt(klines, use_rsi=use_rsi)
            if r:
                print(f"{sym:20s} {label:8s}"
                      f" {r['return']:>+8.2f}%"
                      f" {r['win_rate']:>6.1f}%"
                      f" {r['trades']:>6d}"
                      f" {r['pf']:>6.2f}"
                      f" {r['max_dd']:>7.2f}%"
                      f" {r['sharpe']:>8.2f}"
                      f" {r['calmar']:>8.2f}")
    sep()


# ═══════════════════════════════════════════════════════════════
# 维度 5：多空对比（Long-only vs Long+Short，BTC+ETH 15m）
# ═══════════════════════════════════════════════════════════════

def dim5_long_short():
    print()
    sep('═')
    print("维度 5：多空对比（Long-only vs Long+Short，BTC+ETH 15m，推荐配置）")
    sep('═')
    hdr = f"{'品种':20s} {'方向':14s} {'收益%':>8} {'胜率%':>7} {'交易数':>6} {'PF':>6} {'MaxDD%':>8} {'Sharpe':>8}"
    print(hdr)
    sep()

    for sym in SYMBOLS:
        klines = load_klines(sym, "15m", days=21)
        if not klines:
            continue
        for enable_short, label in [(False, "Long-only"), (True, "Long+Short")]:
            r = run_bt(klines, enable_short=enable_short)
            if r:
                print(f"{sym:20s} {label:14s}"
                      f" {r['return']:>+8.2f}%"
                      f" {r['win_rate']:>6.1f}%"
                      f" {r['trades']:>6d}"
                      f" {r['pf']:>6.2f}"
                      f" {r['max_dd']:>7.2f}%"
                      f" {r['sharpe']:>8.2f}")
    sep()


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 92)
    print("  OKK 策略多维度深度验证  —  TrendFollow EMA双均线  (推荐配置: fast=12 slow=40 sl=1% tp=8%)")
    print("=" * 92)

    dim1_matrix()
    dim2_walk_forward()
    dim3_sensitivity()
    dim4_risk_metrics()
    dim5_long_short()

    print()
    print("=" * 92)
    print("  验证完成")
    print("=" * 92)
    print()
