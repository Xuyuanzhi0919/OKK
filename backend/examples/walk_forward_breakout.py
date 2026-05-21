"""
Walk-forward test for a volatility breakout strategy.

Logic:
- Trend filter: close above/below EMA slow
- Breakout: close breaks prior Donchian high/low
- Volatility filter: ATR / close above threshold
- Risk: fixed fraction of equity, capped by max notional
- Exit: ATR stop, ATR take profit, or EMA trend failure

Example:
    cd backend
    ./venv/bin/python examples/walk_forward_breakout.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP --quiet
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from loguru import logger
from sqlalchemy import func

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal, engine as db_engine
from app.models import Kline
from app.services.backtest.metrics import BacktestMetrics


@dataclass
class Trade:
    timestamp: int
    side: str
    price: float
    amount: float
    fee: float
    pnl: float
    pnl_percent: float


@dataclass
class Result:
    final_equity: float
    metrics: Dict
    params: Dict
    trades: List[Trade]
    equity_curve: List[Dict]


def dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000)


def ts_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def ema(values: List[float], period: int) -> float:
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = value * alpha + result * (1 - alpha)
    return result


def atr(klines: List[Dict], period: int) -> float:
    if len(klines) < period + 1:
        return 0.0
    ranges = []
    for i in range(1, len(klines)):
        high = float(klines[i]["high"])
        low = float(klines[i]["low"])
        prev_close = float(klines[i - 1]["close"])
        ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    recent = ranges[-period:]
    return sum(recent) / len(recent) if recent else 0.0


def load_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> List[Dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Kline)
            .filter(
                Kline.symbol == symbol,
                Kline.interval == interval,
                Kline.timestamp >= start_ms,
                Kline.timestamp <= end_ms,
                Kline.confirm == 1,
            )
            .order_by(Kline.timestamp.asc())
            .all()
        )
        return [
            {
                "timestamp": k.timestamp,
                "open": float(k.open),
                "high": float(k.high),
                "low": float(k.low),
                "close": float(k.close),
                "volume": float(k.volume),
                "volume_currency": float(k.volume_currency),
            }
            for k in rows
        ]
    finally:
        db.close()


def available_range(symbol: str, interval: str, start_ms: int, end_ms: int) -> Tuple[int, int, int]:
    db = SessionLocal()
    try:
        row = (
            db.query(func.min(Kline.timestamp), func.max(Kline.timestamp), func.count(Kline.id))
            .filter(
                Kline.symbol == symbol,
                Kline.interval == interval,
                Kline.timestamp >= start_ms,
                Kline.timestamp <= end_ms,
                Kline.confirm == 1,
            )
            .one()
        )
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    finally:
        db.close()


def candidate_params() -> Iterable[Dict]:
    for ema_period, breakout, atr_period, atr_min, stop_atr, tp_atr, cooldown, risk, max_pos in product(
        [120, 160],
        [36, 48],
        [14],
        [0.006, 0.008],
        [2.4, 3.0],
        [4.5, 6.0],
        [10800],
        [0.005, 0.01],
        [500],
    ):
        if tp_atr <= stop_atr:
            continue
        yield {
            "ema_period": ema_period,
            "breakout_period": breakout,
            "atr_period": atr_period,
            "atr_min": atr_min,
            "stop_atr": stop_atr,
            "tp_atr": tp_atr,
            "cooldown_ms": cooldown * 1000,
            "risk_per_trade": risk,
            "max_position_usd": max_pos,
            "fee_rate": 0.0005,
        }


def run_breakout(symbol: str, klines: List[Dict], initial: float, params: Dict) -> Result:
    capital = initial
    position = ""
    qty = 0.0
    entry = 0.0
    margin = 0.0
    stop = 0.0
    take_profit = 0.0
    last_trade_ts = 0
    trades: List[Trade] = []
    equity_curve: List[Dict] = []

    warmup = max(params["ema_period"], params["breakout_period"], params["atr_period"]) + 2
    for i, kline in enumerate(klines):
        close = float(kline["close"])
        high = float(kline["high"])
        low = float(kline["low"])
        ts = int(kline["timestamp"])

        unrealized = 0.0
        if position == "long":
            unrealized = (close - entry) * qty
        elif position == "short":
            unrealized = (entry - close) * qty

        if position == "long" and (low <= stop or high >= take_profit):
            exit_price = stop if low <= stop else take_profit
            notional = exit_price * qty
            fee = notional * params["fee_rate"]
            pnl = (exit_price - entry) * qty - fee
            before = capital
            capital += margin + pnl
            trades.append(Trade(ts, "sell", exit_price, qty, fee, pnl, pnl / margin * 100 if margin else 0))
            position = ""; qty = entry = margin = stop = take_profit = 0.0; last_trade_ts = ts
        elif position == "short" and (high >= stop or low <= take_profit):
            exit_price = stop if high >= stop else take_profit
            notional = exit_price * qty
            fee = notional * params["fee_rate"]
            pnl = (entry - exit_price) * qty - fee
            before = capital
            capital += margin + pnl
            trades.append(Trade(ts, "buy", exit_price, qty, fee, pnl, pnl / margin * 100 if margin else 0))
            position = ""; qty = entry = margin = stop = take_profit = 0.0; last_trade_ts = ts

        if i >= warmup and not position and ts - last_trade_ts >= params["cooldown_ms"]:
            hist = klines[:i]
            closes = [float(x["close"]) for x in hist]
            trend = ema(closes, params["ema_period"])
            current_atr = atr(hist, params["atr_period"])
            if current_atr > 0 and current_atr / close >= params["atr_min"]:
                prev = hist[-params["breakout_period"]:]
                breakout_high = max(float(x["high"]) for x in prev)
                breakout_low = min(float(x["low"]) for x in prev)
                side = ""
                if close > breakout_high and close > trend:
                    side = "long"
                elif close < breakout_low and close < trend:
                    side = "short"

                if side:
                    equity = capital
                    risk_cap = equity * params["risk_per_trade"]
                    stop_dist = current_atr * params["stop_atr"]
                    size_by_risk = risk_cap / stop_dist
                    size_by_cap = params["max_position_usd"] / close
                    qty = max(0.0, min(size_by_risk, size_by_cap))
                    notional = close * qty
                    margin = notional / 3
                    fee = notional * params["fee_rate"]
                    if qty > 0 and margin + fee <= capital:
                        capital -= margin + fee
                        entry = close
                        position = side
                        if side == "long":
                            stop = close - current_atr * params["stop_atr"]
                            take_profit = close + current_atr * params["tp_atr"]
                            trades.append(Trade(ts, "buy", close, qty, fee, 0.0, 0.0))
                        else:
                            stop = close + current_atr * params["stop_atr"]
                            take_profit = close - current_atr * params["tp_atr"]
                            trades.append(Trade(ts, "sell", close, qty, fee, 0.0, 0.0))

        unrealized = 0.0
        if position == "long":
            unrealized = (close - entry) * qty
        elif position == "short":
            unrealized = (entry - close) * qty
        equity_curve.append({
            "timestamp": ts,
            "equity": capital + margin + unrealized,
            "capital": capital,
            "position_value": margin,
            "unrealized_pnl": unrealized,
            "position_direction": position or "flat",
            "leverage": 3,
        })

    if position and klines:
        close = float(klines[-1]["close"])
        ts = int(klines[-1]["timestamp"])
        fee = close * qty * params["fee_rate"]
        pnl = ((close - entry) * qty if position == "long" else (entry - close) * qty) - fee
        capital += margin + pnl
        trades.append(Trade(ts, "sell" if position == "long" else "buy", close, qty, fee, pnl, pnl / margin * 100 if margin else 0))

    final = equity_curve[-1]["equity"] if equity_curve else initial
    trade_dicts = [t.__dict__ for t in trades]
    metrics = BacktestMetrics.calculate_all_metrics(initial, final, equity_curve, trade_dicts, int(klines[0]["timestamp"]), int(klines[-1]["timestamp"]))
    return Result(final, metrics, params, trades, equity_curve)


def score(result: Result) -> float:
    m = result.metrics
    trades = int(m["total_trades"])
    if trades < 4:
        return -999
    return float(m["total_return"]) * 100 + min(float(m["profit_factor"]), 3) * 0.25 - float(m["max_drawdown"]) * 80 - abs(trades - 20) * 0.003


def best_train(symbol: str, klines: List[Dict], initial: float) -> Result:
    best = None
    best_score = -10**9
    for params in candidate_params():
        result = run_breakout(symbol, klines, initial, params)
        value = score(result)
        if value > best_score:
            best = result
            best_score = value
    if best is None:
        raise RuntimeError("No result")
    return best


def walk_forward(symbol: str, interval: str, start_ms: int, end_ms: int, train_days: int, test_days: int, initial: float):
    data_start, data_end, count = available_range(symbol, interval, start_ms, end_ms)
    print(f"\n=== {symbol} {interval} data={dt(data_start):%Y-%m-%d %H:%M} -> {dt(data_end):%Y-%m-%d %H:%M}, n={count} ===")
    fold_start = data_start
    validations = []
    fold = 1
    while True:
        train_start = fold_start
        train_end = train_start + train_days * 86400 * 1000
        test_start = train_end
        test_end = test_start + test_days * 86400 * 1000
        if test_end > data_end:
            break
        train = load_klines(symbol, interval, train_start, train_end)
        test = load_klines(symbol, interval, test_start, test_end)
        if len(train) < 300 or len(test) < 100:
            break
        train_result = best_train(symbol, train, initial)
        validation = run_breakout(symbol, test, initial, train_result.params)
        validations.append(validation)
        p = train_result.params
        tm = train_result.metrics
        vm = validation.metrics
        print(
            f"fold {fold}: train {dt(train_start):%m-%d}->{dt(train_end):%m-%d} "
            f"ret={tm['total_return']:.2%} dd={tm['max_drawdown']:.2%} pf={tm['profit_factor']:.2f}; "
            f"test {dt(test_start):%m-%d}->{dt(test_end):%m-%d} "
            f"ret={vm['total_return']:.2%} dd={vm['max_drawdown']:.2%} pf={vm['profit_factor']:.2f} trades={vm['total_trades']} | "
            f"ema={p['ema_period']} br={p['breakout_period']} atrMin={p['atr_min']} stop={p['stop_atr']} tp={p['tp_atr']} "
            f"risk={p['risk_per_trade']:.1%} maxPos={p['max_position_usd']}"
        )
        fold += 1
        fold_start += test_days * 86400 * 1000

    if validations:
        rets = [float(v.metrics["total_return"]) for v in validations]
        dds = [float(v.metrics["max_drawdown"]) for v in validations]
        pfs = [float(v.metrics["profit_factor"]) for v in validations]
        print(
            f"SUMMARY {symbol}: folds={len(validations)} positive={sum(1 for r in rets if r > 0)}/{len(validations)} "
            f"avg_ret={sum(rets)/len(rets):.2%} total_ret_sum={sum(rets):.2%} max_dd={max(dds):.2%} avg_pf={sum(pfs)/len(pfs):.2f}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    parser.add_argument("--interval", default="1H")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--initial-capital", type=float, default=1000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.quiet:
        logger.remove()
        db_engine.echo = False
    end = datetime.now()
    start = end - timedelta(days=args.days)
    print(f"breakout walk-forward interval={args.interval} range={start:%Y-%m-%d} -> {end:%Y-%m-%d}")
    for symbol in args.symbols:
        walk_forward(symbol, args.interval, ts_ms(start), ts_ms(end), args.train_days, args.test_days, args.initial_capital)


if __name__ == "__main__":
    main()
