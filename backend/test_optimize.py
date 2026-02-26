"""
策略优化器 C = A（参数网格搜索） + B（趋势/RSI/成交量过滤条件）

流程：
  1. 在 BTC/ETH 15m 14天数据上跑 256 组参数组合（方向 A）
  2. 取综合得分 Top 5，叠加三种过滤条件重新回测（方向 B）
  3. 对比有无过滤条件的差异，输出最终推荐参数
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import itertools
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from loguru import logger
from app.core.database import SessionLocal
from app.services.backtest.backtest_engine import BacktestEngine
from app.models import Kline
from sqlalchemy import and_

logger.remove()
logger.add(sys.stderr, level="WARNING")   # 只保留 WARNING+ 减少噪声


# ─────────────────────────────────────────────
# 策略引擎（支持过滤条件）
# ─────────────────────────────────────────────

class TrendFollowEngineV2(BacktestEngine):
    """EMA 双均线趋势跟踪策略（含可选过滤条件）"""

    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        fast_period: int = 7,
        slow_period: int = 30,
        amount_per_trade: float = 0.01,
        fee_rate: float = 0.0005,
        stop_loss_percent: float = 0.01,
        take_profit_percent: float = 0.05,
        # 过滤条件开关
        use_trend_filter: bool = False,   # 价格 > EMA(100) 才开多
        use_rsi_filter: bool = False,     # RSI(14) < rsi_threshold 才开多
        rsi_threshold: float = 65.0,
        use_volume_filter: bool = False,  # 当根成交量 > vol_ma(10) 才开多
    ):
        super().__init__(
            symbol=symbol,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            leverage=1,
            enable_short=False,
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.amount_per_trade = amount_per_trade
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent

        self.use_trend_filter = use_trend_filter
        self.use_rsi_filter = use_rsi_filter
        self.rsi_threshold = rsi_threshold
        self.use_volume_filter = use_volume_filter

        self.price_history: List[float] = []
        self.volume_history: List[float] = []
        self.fast_ema_history: List[float] = []
        self.slow_ema_history: List[float] = []
        self.trend_ema_history: List[float] = []   # EMA(100)
        self.entry_price: float = 0.0

        # 用于 max drawdown 计算
        self.peak_equity: float = initial_capital
        self.max_drawdown: float = 0.0

    def reset(self):
        super().reset()
        self.price_history = []
        self.volume_history = []
        self.fast_ema_history = []
        self.slow_ema_history = []
        self.trend_ema_history = []
        self.entry_price = 0.0
        self.peak_equity = self.initial_capital
        self.max_drawdown = 0.0

    # ── 指标计算 ──────────────────────────────

    @staticmethod
    def _ema_next(prev_ema: Optional[float], price: float, period: int,
                  prices: List[float]) -> float:
        """增量 EMA；数据不足时用简单均值初始化"""
        k = 2 / (period + 1)
        if prev_ema is None:
            if len(prices) < period:
                return sum(prices) / len(prices)
            return sum(prices[-period:]) / period
        return (price - prev_ema) * k + prev_ema

    @staticmethod
    def _rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(-period, 0):
            d = prices[i] - prices[i - 1]
            (gains if d > 0 else losses).append(abs(d))
        avg_g = sum(gains) / period
        avg_l = sum(losses) / period
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return 100.0 - 100.0 / (1 + rs)

    @staticmethod
    def _vol_ma(volumes: List[float], period: int = 10) -> float:
        if len(volumes) < period:
            return volumes[-1] if volumes else 0.0
        return sum(volumes[-period:]) / period

    # ── 主逻辑 ───────────────────────────────

    def _update_equity(self, price: float):
        """更新 max drawdown"""
        equity = self.capital
        if self.position.amount > 0:
            equity += self.position.amount * price - self.position.amount * self.position.avg_price
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if dd > self.max_drawdown:
            self.max_drawdown = dd

    def on_kline(self, kline: Dict):
        ts = int(kline['timestamp'])
        close = float(kline['close'])
        vol = float(kline['volume'])

        self.price_history.append(close)
        self.volume_history.append(vol)
        self.current_kline = kline

        # 计算 EMA
        prev_fast = self.fast_ema_history[-1] if self.fast_ema_history else None
        prev_slow = self.slow_ema_history[-1] if self.slow_ema_history else None
        prev_trend = self.trend_ema_history[-1] if self.trend_ema_history else None

        fast_ema = self._ema_next(prev_fast, close, self.fast_period, self.price_history)
        slow_ema = self._ema_next(prev_slow, close, self.slow_period, self.price_history)
        trend_ema = self._ema_next(prev_trend, close, 100, self.price_history)

        self.fast_ema_history.append(fast_ema)
        self.slow_ema_history.append(slow_ema)
        self.trend_ema_history.append(trend_ema)

        self._update_equity(close)

        # 热身期
        if len(self.price_history) < self.slow_period + 2:
            return

        prev_fast_val = self.fast_ema_history[-2]
        prev_slow_val = self.slow_ema_history[-2]
        has_long = self.position.amount > 0

        # 止损 / 止盈（优先于信号）
        if has_long and self.entry_price > 0:
            pnl_pct = (close - self.entry_price) / self.entry_price
            if pnl_pct <= -self.stop_loss_percent:
                self.sell(close, self.position.amount, ts)
                self.entry_price = 0.0
                return
            if pnl_pct >= self.take_profit_percent:
                self.sell(close, self.position.amount, ts)
                self.entry_price = 0.0
                return

        golden = prev_fast_val <= prev_slow_val and fast_ema > slow_ema
        death = prev_fast_val >= prev_slow_val and fast_ema < slow_ema

        # 开多信号 + 过滤条件
        if not has_long and golden:
            if self.use_trend_filter and close < trend_ema:
                return
            if self.use_rsi_filter and self._rsi(self.price_history) >= self.rsi_threshold:
                return
            if self.use_volume_filter and vol < self._vol_ma(self.volume_history):
                return
            t = self.buy(close, self.amount_per_trade, ts)
            if t:
                self.entry_price = close

        # 平多信号
        elif has_long and death:
            t = self.sell(close, self.position.amount, ts)
            if t:
                self.entry_price = 0.0


# ─────────────────────────────────────────────
# 回测运行器
# ─────────────────────────────────────────────

def run_backtest(
    klines: list,
    fast_period: int,
    slow_period: int,
    stop_loss: float,
    take_profit: float,
    initial_capital: float = 10000.0,
    position_ratio: float = 0.4,
    use_trend_filter: bool = False,
    use_rsi_filter: bool = False,
    use_volume_filter: bool = False,
) -> Optional[Dict]:
    if not klines:
        return None

    first_price = float(klines[0].open)
    last_price = float(klines[-1].close)
    amount_per_trade = initial_capital * position_ratio / first_price

    engine = TrendFollowEngineV2(
        symbol="",
        initial_capital=initial_capital,
        fast_period=fast_period,
        slow_period=slow_period,
        amount_per_trade=amount_per_trade,
        fee_rate=0.0005,
        stop_loss_percent=stop_loss,
        take_profit_percent=take_profit,
        use_trend_filter=use_trend_filter,
        use_rsi_filter=use_rsi_filter,
        use_volume_filter=use_volume_filter,
    )

    for k in klines:
        engine.on_kline({
            'timestamp': k.timestamp,
            'open': k.open,
            'high': k.high,
            'low': k.low,
            'close': k.close,
            'volume': k.volume,
        })

    # 最终持仓按收盘价估值
    final = engine.capital
    if engine.position.amount > 0:
        unrealized = (last_price - engine.position.avg_price) * engine.position.amount
        final += unrealized

    closed = [t for t in engine.trades if t.side == 'sell']
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]

    win_rate = len(wins) / len(closed) * 100 if closed else 0.0
    total_win = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))
    profit_factor = total_win / total_loss if total_loss > 0 else (99.0 if total_win > 0 else 0.0)
    total_return = (final - initial_capital) / initial_capital * 100

    # 综合得分：收益率 × 胜率 / max(回撤, 1)
    score = total_return * (win_rate / 100) / max(engine.max_drawdown, 1.0)

    return {
        'fast': fast_period,
        'slow': slow_period,
        'sl': stop_loss,
        'tp': take_profit,
        'return': round(total_return, 2),
        'win_rate': round(win_rate, 1),
        'trades': len(closed),
        'profit_factor': round(profit_factor, 2),
        'max_dd': round(engine.max_drawdown, 2),
        'score': round(score, 4),
        'filters': f"{'T' if use_trend_filter else '-'}{'R' if use_rsi_filter else '-'}{'V' if use_volume_filter else '-'}",
    }


# ─────────────────────────────────────────────
# 数据加载
# ─────────────────────────────────────────────

def load_klines(symbol: str, interval: str, days: int) -> list:
    db = SessionLocal()
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        return db.query(Kline).filter(
            and_(
                Kline.symbol == symbol,
                Kline.interval == interval,
                Kline.timestamp >= int(start_time.timestamp() * 1000),
                Kline.timestamp <= int(end_time.timestamp() * 1000),
            )
        ).order_by(Kline.timestamp.asc()).all()
    finally:
        db.close()


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

async def main():
    print("\n" + "=" * 90)
    print("策略优化器  C = A（参数网格搜索）+ B（过滤条件）")
    print("=" * 90)

    # ── 参数网格 ──────────────────────────────
    PARAM_GRID = {
        'fast_period':   [5, 7, 9, 12],
        'slow_period':   [20, 30, 40, 55],
        'stop_loss':     [0.01, 0.015, 0.02, 0.03],
        'take_profit':   [0.03, 0.05, 0.08, 0.10],
    }
    combos = list(itertools.product(
        PARAM_GRID['fast_period'],
        PARAM_GRID['slow_period'],
        PARAM_GRID['stop_loss'],
        PARAM_GRID['take_profit'],
    ))
    total = len(combos)
    print(f"\n参数组合总数: {total}  (4×4×4×4 = {total})")

    SYMBOLS   = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    INTERVAL  = "15m"
    GRID_DAYS = 14    # 网格搜索用 14 天（最多数据）
    VALID_DAYS = 7    # 验证集用 7 天

    # ── 获取 K 线 ─────────────────────────────
    print(f"\n加载 K 线数据 ({INTERVAL}, {GRID_DAYS}天 + {VALID_DAYS}天)...")
    from app.services.exchange.okx import OKXExchange
    from app.services.backtest.kline_service import KlineService

    for symbol in SYMBOLS:
        for days in sorted(set([GRID_DAYS, VALID_DAYS])):
            db = SessionLocal()
            try:
                exchange = OKXExchange(api_key="", secret_key="", passphrase="", simulated=True)
                svc = KlineService(db, exchange)
                end_t = datetime.now()
                start_t = end_t - timedelta(days=days)
                await svc.fetch_and_save_klines(
                    symbol=symbol, interval=INTERVAL,
                    start_time=int(start_t.timestamp() * 1000),
                    end_time=int(end_t.timestamp() * 1000),
                )
                await exchange.close()
            except Exception as e:
                print(f"  警告: 拉取 {symbol} {days}天失败: {e}")
            finally:
                db.close()
            await asyncio.sleep(0.3)

    klines_grid  = {s: load_klines(s, INTERVAL, GRID_DAYS)  for s in SYMBOLS}
    klines_valid = {s: load_klines(s, INTERVAL, VALID_DAYS) for s in SYMBOLS}

    for s in SYMBOLS:
        print(f"  {s}: {len(klines_grid[s])} 根(训练) / {len(klines_valid[s])} 根(验证)")

    # ── 方向 A：网格搜索 ────────────────────────
    print(f"\n{'─'*90}")
    print(f"方向 A：参数网格搜索（{INTERVAL} {GRID_DAYS}天）")
    print(f"{'─'*90}")

    all_results = []
    for idx, (fp, sp, sl, tp) in enumerate(combos, 1):
        if fp >= sp:          # fast 必须小于 slow
            continue
        row = {'fast': fp, 'slow': sp, 'sl': sl, 'tp': tp}
        returns, scores = [], []
        valid = True
        for sym in SYMBOLS:
            r = run_backtest(klines_grid[sym], fp, sp, sl, tp)
            if r is None:
                valid = False
                break
            row[f'ret_{sym[:3]}'] = r['return']
            row[f'wr_{sym[:3]}']  = r['win_rate']
            row[f'dd_{sym[:3]}']  = r['max_dd']
            row[f'tr_{sym[:3]}']  = r['trades']
            returns.append(r['return'])
            scores.append(r['score'])
        if not valid:
            continue
        row['avg_return'] = round(sum(returns) / len(returns), 2)
        row['avg_score']  = round(sum(scores)  / len(scores),  4)
        all_results.append(row)

    # 按综合得分排序
    all_results.sort(key=lambda x: x['avg_score'], reverse=True)

    print(f"\n{'快线':>5} {'慢线':>5} {'止损':>6} {'止盈':>6}  "
          f"{'BTC收益':>8} {'BTC胜率':>7} {'ETH收益':>8} {'ETH胜率':>7}  "
          f"{'均收益':>8} {'综合分':>8}")
    print("─" * 90)
    for r in all_results[:20]:
        b, e = r.get('ret_BTC', 0), r.get('ret_ETH', 0)
        bw, ew = r.get('wr_BTC', 0), r.get('wr_ETH', 0)
        print(f"  {r['fast']:>3}   {r['slow']:>3}  {r['sl']*100:>5.1f}%  {r['tp']*100:>5.1f}%  "
              f"  {b:>+7.2f}%  {bw:>5.1f}%   {e:>+7.2f}%  {ew:>5.1f}%  "
              f"  {r['avg_return']:>+7.2f}%  {r['avg_score']:>8.4f}")

    TOP_N = 5
    top_params = all_results[:TOP_N]

    print(f"\n→ Top {TOP_N} 参数组合：", [(r['fast'], r['slow'], r['sl'], r['tp']) for r in top_params])

    # ── 验证集交叉验证（7天） ────────────────────
    print(f"\n{'─'*90}")
    print(f"交叉验证：Top {TOP_N} 参数在 {VALID_DAYS}天验证集上的表现")
    print(f"{'─'*90}")
    print(f"\n{'快线':>5} {'慢线':>5} {'止损':>6} {'止盈':>6}  "
          f"{'BTC收益(验证)':>13} {'ETH收益(验证)':>13}  {'均收益':>8}")
    print("─" * 70)
    for r in top_params:
        vrets = []
        for sym in SYMBOLS:
            vr = run_backtest(klines_valid[sym], r['fast'], r['slow'], r['sl'], r['tp'])
            vrets.append(vr['return'] if vr else 0)
        print(f"  {r['fast']:>3}   {r['slow']:>3}  {r['sl']*100:>5.1f}%  {r['tp']*100:>5.1f}%  "
              f"  {vrets[0]:>+10.2f}%    {vrets[1]:>+10.2f}%    {sum(vrets)/len(vrets):>+7.2f}%")

    # ── 方向 B：过滤条件对比 ────────────────────
    print(f"\n{'─'*90}")
    print(f"方向 B：过滤条件对比（{INTERVAL} {GRID_DAYS}天，取 Top {TOP_N} 参数）")
    print("  过滤标记: T=趋势(EMA100)  R=RSI(<65)  V=成交量(>10MA)")
    print(f"{'─'*90}")

    filter_combos = [
        (False, False, False),   # 无过滤（基准）
        (True,  False, False),   # 仅趋势
        (False, True,  False),   # 仅 RSI
        (False, False, True),    # 仅成交量
        (True,  True,  False),   # 趋势 + RSI
        (True,  False, True),    # 趋势 + 成交量
        (True,  True,  True),    # 全部
    ]

    print(f"\n{'过滤':>5}  {'快线':>4} {'慢线':>4} {'止损':>6} {'止盈':>6}  "
          f"{'BTC收益':>8} {'BTC胜率':>7} {'BTC交易':>7}  "
          f"{'ETH收益':>8} {'ETH胜率':>7} {'ETH交易':>7}  {'均收益':>8}")
    print("─" * 120)

    best_filter_results = []
    for r in top_params:
        for (tf, rf, vf) in filter_combos:
            row_rets, row_wrs = [], []
            filter_tag = f"{'T' if tf else '-'}{'R' if rf else '-'}{'V' if vf else '-'}"
            cols = [f"  {filter_tag:<5}  {r['fast']:>4} {r['slow']:>4}  {r['sl']*100:>5.1f}%  {r['tp']*100:>5.1f}%"]
            for sym in SYMBOLS:
                fr = run_backtest(klines_grid[sym], r['fast'], r['slow'], r['sl'], r['tp'],
                                  use_trend_filter=tf, use_rsi_filter=rf, use_volume_filter=vf)
                ret = fr['return'] if fr else 0
                wr  = fr['win_rate'] if fr else 0
                trd = fr['trades'] if fr else 0
                cols.append(f"  {ret:>+7.2f}%  {wr:>5.1f}%  {trd:>6}")
                row_rets.append(ret)
                row_wrs.append(wr)
            avg_ret = sum(row_rets) / len(row_rets)
            cols.append(f"  {avg_ret:>+7.2f}%")
            print("".join(cols))
            best_filter_results.append({
                'fast': r['fast'], 'slow': r['slow'], 'sl': r['sl'], 'tp': r['tp'],
                'filter': filter_tag, 'avg_return': avg_ret,
                'avg_wr': sum(row_wrs) / len(row_wrs),
            })
        print()   # 每组参数间空行

    # ── 最终推荐 ────────────────────────────────
    best_filter_results.sort(key=lambda x: x['avg_return'], reverse=True)
    best = best_filter_results[0]

    print(f"\n{'=' * 90}")
    print("最终推荐配置")
    print(f"{'=' * 90}")
    print(f"  EMA 快线:   {best['fast']}")
    print(f"  EMA 慢线:   {best['slow']}")
    print(f"  止损:       {best['sl']*100:.1f}%")
    print(f"  止盈:       {best['tp']*100:.1f}%")
    print(f"  过滤条件:   {best['filter']}  (T=趋势EMA100 R=RSI<65 V=成交量>10MA)")
    print(f"  平均收益率: {best['avg_return']:+.2f}%")
    print(f"  平均胜率:   {best['avg_wr']:.1f}%")
    print(f"\n{'=' * 90}")
    print("优化完成")
    print(f"{'=' * 90}\n")


if __name__ == "__main__":
    asyncio.run(main())
