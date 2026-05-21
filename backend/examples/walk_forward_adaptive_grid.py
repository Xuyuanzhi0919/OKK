"""
Walk-forward test for adaptive_grid_trend.

Example:
    cd backend
    ./venv/bin/python examples/walk_forward_adaptive_grid.py \
      --symbols BTC-USDT-SWAP ETH-USDT-SWAP \
      --interval 1H \
      --days 180 \
      --train-days 60 \
      --test-days 30
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
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

from app.core.config import settings
from app.core.database import SessionLocal, engine as db_engine
from app.models import Kline
from app.services.backtest.adaptive_grid_trend_backtest import AdaptiveGridTrendBacktestEngine
from app.services.backtest.kline_service import KlineService
from app.services.backtest.metrics import BacktestMetrics
from app.services.exchange.okx import OKXExchange


@dataclass
class RunResult:
    metrics: Dict
    params: Dict
    final_equity: float


def dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000)


def ts_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def kline_to_dict(k: Kline) -> Dict:
    return {
        "timestamp": k.timestamp,
        "open": float(k.open),
        "high": float(k.high),
        "low": float(k.low),
        "close": float(k.close),
        "volume": float(k.volume),
        "volume_currency": float(k.volume_currency),
    }


def candidate_params(search: str = "focused") -> Iterable[Dict]:
    base = {
        "direction": "both",
        "atr_period": 14,
        "fee_rate": 0.0005,
        "leverage": 3,
    }

    if search == "focused":
        for fast, slow, entry, stop, tp, cooldown in product(
            [12, 20, 30],
            [80, 120, 160],
            [0.25, 0.6],
            [1.8, 2.8],
            [3.2, 4.5, 6.0],
            [60 * 60, 120 * 60],
        ):
            if fast >= slow:
                continue
            yield {
                **base,
                "fast_period": fast,
                "slow_period": slow,
                "entry_atr_multiple": entry,
                "stop_atr_multiple": stop,
                "take_profit_atr_multiple": tp,
                "cooldown_seconds": cooldown,
                "risk_per_trade": 0.01,
                "max_position_usd": 500,
            }
        return

    if search == "wide":
        for fast, slow, entry, stop, tp, cooldown, risk, max_pos in product(
            [8, 12, 20, 30, 45],
            [60, 90, 120, 160, 200],
            [0.0, 0.25, 0.6, 0.9, 1.2],
            [1.5, 1.8, 2.4, 2.8, 3.5],
            [2.4, 3.2, 4.5, 6.0, 8.0],
            [30 * 60, 60 * 60, 120 * 60, 240 * 60],
            [0.005, 0.01],
            [300, 500],
        ):
            if fast >= slow:
                continue
            yield {
                **base,
                "fast_period": fast,
                "slow_period": slow,
                "entry_atr_multiple": entry,
                "stop_atr_multiple": stop,
                "take_profit_atr_multiple": tp,
                "cooldown_seconds": cooldown,
                "risk_per_trade": risk,
                "max_position_usd": max_pos,
            }
        return

    # Representative sets from prior BTC 30d search plus nearby conservative variants.
    # Keeping this list short makes walk-forward practical and reduces overfitting.
    presets = [
        (12, 120, 0.60, 2.8, 4.5, 7200, 0.010, 500),
        (12, 120, 0.60, 2.8, 5.5, 7200, 0.010, 500),
        (20, 90, 0.15, 1.8, 5.5, 7200, 0.010, 500),
        (20, 90, 0.15, 2.2, 2.8, 14400, 0.010, 500),
        (20, 120, 0.15, 2.2, 2.8, 14400, 0.010, 500),
        (20, 120, 0.60, 2.8, 5.5, 7200, 0.010, 500),
        (30, 90, 0.35, 1.8, 2.8, 7200, 0.010, 500),
        (30, 90, 0.35, 1.5, 2.8, 14400, 0.010, 500),
        (30, 120, 0.60, 2.2, 5.5, 7200, 0.010, 500),
        (30, 120, 0.90, 2.2, 5.5, 7200, 0.010, 500),
        (12, 120, 0.60, 2.8, 4.5, 7200, 0.005, 300),
        (20, 120, 0.60, 2.8, 5.5, 14400, 0.005, 300),
    ]
    for fast, slow, entry, stop, tp, cooldown, risk, max_pos in presets:
        yield {
            **base,
            "fast_period": fast,
            "slow_period": slow,
            "entry_atr_multiple": entry,
            "stop_atr_multiple": stop,
            "take_profit_atr_multiple": tp,
            "cooldown_seconds": cooldown,
            "risk_per_trade": risk,
            "max_position_usd": max_pos,
        }


def run_engine(symbol: str, klines: List[Dict], initial_capital: float, params: Dict) -> RunResult:
    engine = AdaptiveGridTrendBacktestEngine.from_params(symbol, initial_capital, params)
    result = engine.run(klines)
    trades = [
        {
            "timestamp": t.timestamp,
            "side": t.side,
            "price": t.price,
            "amount": t.amount,
            "fee": t.fee,
            "pnl": t.pnl,
            "pnl_percent": t.pnl_percent,
        }
        for t in engine.trades
    ]
    metrics = BacktestMetrics.calculate_all_metrics(
        initial_capital=initial_capital,
        final_capital=result["final_equity"],
        equity_curve=engine.equity_curve,
        trades=trades,
        start_timestamp=int(klines[0]["timestamp"]),
        end_timestamp=int(klines[-1]["timestamp"]),
    )
    return RunResult(metrics=metrics, params=params, final_equity=result["final_equity"])


def score_result(result: RunResult) -> float:
    metrics = result.metrics
    ret = float(metrics.get("total_return") or 0)
    dd = float(metrics.get("max_drawdown") or 0)
    pf = float(metrics.get("profit_factor") or 0)
    trades = int(metrics.get("total_trades") or 0)

    if trades < 6:
        return -999
    if dd <= 0:
        dd = 0.001
    # Return is the main objective, but the penalty prevents high-return/high-blowup sets
    # from dominating the walk-forward selection.
    return ret * 140 + min(pf, 3) * 0.20 - dd * 70 - abs(trades - 30) * 0.003


def best_on_train(symbol: str, train_klines: List[Dict], initial_capital: float, search: str) -> RunResult:
    best: RunResult | None = None
    best_score = -10**9
    for params in candidate_params(search):
        result = run_engine(symbol, train_klines, initial_capital, params)
        score = score_result(result)
        if score > best_score:
            best = result
            best_score = score
    if best is None:
        raise RuntimeError("No candidate parameter set produced a result")
    return best


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
        return [kline_to_dict(k) for k in rows]
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


async def fetch_data(symbols: List[str], interval: str, start_ms: int, end_ms: int):
    exchange = OKXExchange(
        api_key=settings.OKX_API_KEY,
        secret_key=settings.OKX_SECRET_KEY,
        passphrase=settings.OKX_PASSPHRASE,
        simulated=settings.OKX_SIMULATED,
        proxy=settings.OKX_PROXY,
    )
    db = SessionLocal()
    try:
        service = KlineService(db, exchange)
        for symbol in symbols:
            print(f"\nFETCH {symbol} {interval}: {dt(start_ms):%Y-%m-%d} -> {dt(end_ms):%Y-%m-%d}")
            result = await service.fetch_and_save_klines(symbol, interval, start_ms, end_ms)
            print(f"  fetched total={result['total']} new={result['new']} updated={result['updated']} skipped={result['skipped']}")
    finally:
        await exchange.close()
        db.close()


def param_key(params: Dict) -> Tuple:
    return (
        params["fast_period"],
        params["slow_period"],
        params["entry_atr_multiple"],
        params["stop_atr_multiple"],
        params["take_profit_atr_multiple"],
        params["cooldown_seconds"],
        params["risk_per_trade"],
        params["max_position_usd"],
    )


def format_params(params: Dict) -> str:
    return (
        f"fast={params['fast_period']} slow={params['slow_period']} "
        f"entry={params['entry_atr_multiple']} stop={params['stop_atr_multiple']} "
        f"tp={params['take_profit_atr_multiple']} risk={params['risk_per_trade']:.1%} "
        f"maxPos={params['max_position_usd']} cd={params['cooldown_seconds']//60}m"
    )


def walk_forward(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    train_days: int,
    test_days: int,
    initial_capital: float,
    search: str,
) -> Dict | None:
    data_start, data_end, count = available_range(symbol, interval, start_ms, end_ms)
    if count == 0:
        print(f"\n{symbol}: no data")
        return None

    print(f"\n=== {symbol} {interval} data={dt(data_start):%Y-%m-%d %H:%M} -> {dt(data_end):%Y-%m-%d %H:%M}, n={count} ===")
    fold_start = data_start
    fold_idx = 1
    validations: List[RunResult] = []
    selected_params: List[Dict] = []

    while True:
        train_start = fold_start
        train_end = train_start + train_days * 24 * 60 * 60 * 1000
        test_start = train_end
        test_end = test_start + test_days * 24 * 60 * 60 * 1000
        if test_end > data_end:
            break

        train_klines = load_klines(symbol, interval, train_start, train_end)
        test_klines = load_klines(symbol, interval, test_start, test_end)
        if len(train_klines) < 150 or len(test_klines) < 50:
            break

        best_train = best_on_train(symbol, train_klines, initial_capital, search)
        validation = run_engine(symbol, test_klines, initial_capital, best_train.params)
        validations.append(validation)
        selected_params.append(best_train.params)

        p = best_train.params
        tm = best_train.metrics
        vm = validation.metrics
        print(
            f"fold {fold_idx}: train {dt(train_start):%m-%d}->{dt(train_end):%m-%d} "
            f"ret={tm['total_return']:.2%} dd={tm['max_drawdown']:.2%} pf={tm['profit_factor']:.2f}; "
            f"test {dt(test_start):%m-%d}->{dt(test_end):%m-%d} "
            f"ret={vm['total_return']:.2%} dd={vm['max_drawdown']:.2%} pf={vm['profit_factor']:.2f} "
            f"trades={vm['total_trades']} | "
            f"{format_params(p)}"
        )

        fold_idx += 1
        fold_start += test_days * 24 * 60 * 60 * 1000

    if not validations:
        print("  no validation folds")
        return None

    returns = [float(v.metrics["total_return"]) for v in validations]
    dds = [float(v.metrics["max_drawdown"]) for v in validations]
    pfs = [float(v.metrics["profit_factor"]) for v in validations]
    trades = [int(v.metrics["total_trades"]) for v in validations]
    positive = sum(1 for r in returns if r > 0)
    param_counts = Counter(param_key(p) for p in selected_params)
    most_common_key, most_common_count = param_counts.most_common(1)[0]
    most_common_params = next(p for p in selected_params if param_key(p) == most_common_key)
    avg_ret = sum(returns) / len(returns)
    max_dd = max(dds)
    avg_pf = sum(pfs) / len(pfs)
    print(
        f"SUMMARY {symbol}: folds={len(validations)} positive={positive}/{len(validations)} "
        f"avg_ret={avg_ret:.2%} total_ret_sum={sum(returns):.2%} "
        f"max_dd={max_dd:.2%} avg_pf={avg_pf:.2f} total_trades={sum(trades)}"
    )
    print(
        f"STABLE_PARAM {symbol}: selected={most_common_count}/{len(selected_params)} "
        f"{format_params(most_common_params)}"
    )

    return {
        "symbol": symbol,
        "folds": len(validations),
        "positive": positive,
        "avg_ret": avg_ret,
        "sum_ret": sum(returns),
        "max_dd": max_dd,
        "avg_pf": avg_pf,
        "total_trades": sum(trades),
        "stable_params": most_common_params,
        "stable_count": most_common_count,
    }


def rolling_windows(data_start: int, data_end: int, warmup_days: int, test_days: int) -> Iterable[Tuple[int, int]]:
    test_start = data_start + warmup_days * 24 * 60 * 60 * 1000
    test_ms = test_days * 24 * 60 * 60 * 1000
    while test_start + test_ms <= data_end:
        yield test_start, test_start + test_ms
        test_start += test_ms


def static_rank(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    warmup_days: int,
    test_days: int,
    initial_capital: float,
    search: str,
    top_n: int,
) -> List[Dict]:
    data_start, data_end, count = available_range(symbol, interval, start_ms, end_ms)
    if count == 0:
        print(f"\n{symbol}: no data")
        return []

    windows = list(rolling_windows(data_start, data_end, warmup_days, test_days))
    if not windows:
        print(f"\n{symbol}: no static rank windows")
        return []

    print(
        f"\n=== STATIC RANK {symbol} {interval}: windows={len(windows)} "
        f"warmup={warmup_days}d test={test_days}d candidates={sum(1 for _ in candidate_params(search))} ==="
    )

    ranked = []
    for params in candidate_params(search):
        validations: List[RunResult] = []
        for test_start, test_end in windows:
            window_start = test_start - warmup_days * 24 * 60 * 60 * 1000
            klines = load_klines(symbol, interval, window_start, test_end)
            if len(klines) < 150:
                continue

            warmup_cutoff = test_start
            engine = AdaptiveGridTrendBacktestEngine.from_params(symbol, initial_capital, params)
            engine.run(klines)
            filtered_trades = [
                {
                    "timestamp": t.timestamp,
                    "side": t.side,
                    "price": t.price,
                    "amount": t.amount,
                    "fee": t.fee,
                    "pnl": t.pnl,
                    "pnl_percent": t.pnl_percent,
                }
                for t in engine.trades
                if t.timestamp >= warmup_cutoff
            ]
            filtered_curve = [
                point
                for point in engine.equity_curve
                if int(point["timestamp"]) >= warmup_cutoff
            ]
            if not filtered_curve:
                continue

            start_equity = filtered_curve[0]["equity"]
            final_equity = filtered_curve[-1]["equity"]
            metrics = BacktestMetrics.calculate_all_metrics(
                initial_capital=start_equity,
                final_capital=final_equity,
                equity_curve=filtered_curve,
                trades=filtered_trades,
                start_timestamp=test_start,
                end_timestamp=test_end,
            )
            validations.append(RunResult(metrics=metrics, params=params, final_equity=final_equity))

        if len(validations) != len(windows):
            continue

        returns = [float(v.metrics["total_return"]) for v in validations]
        dds = [float(v.metrics["max_drawdown"]) for v in validations]
        pfs = [float(v.metrics["profit_factor"]) for v in validations]
        trades = [int(v.metrics["total_trades"]) for v in validations]
        positive = sum(1 for value in returns if value > 0)
        avg_ret = sum(returns) / len(returns)
        max_dd = max(dds)
        avg_pf = sum(pfs) / len(pfs)
        min_ret = min(returns)
        score = avg_ret * 120 + min(avg_pf, 3) * 0.2 - max_dd * 70 + positive * 0.15 + min_ret * 20
        ranked.append({
            "params": params,
            "score": score,
            "avg_ret": avg_ret,
            "sum_ret": sum(returns),
            "min_ret": min_ret,
            "positive": positive,
            "folds": len(windows),
            "max_dd": max_dd,
            "avg_pf": avg_pf,
            "total_trades": sum(trades),
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    for idx, row in enumerate(ranked[:top_n], start=1):
        print(
            f"rank {idx}: score={row['score']:.2f} avg_ret={row['avg_ret']:.2%} "
            f"min_ret={row['min_ret']:.2%} positive={row['positive']}/{row['folds']} "
            f"max_dd={row['max_dd']:.2%} avg_pf={row['avg_pf']:.2f} trades={row['total_trades']} | "
            f"{format_params(row['params'])}"
        )
    return ranked[:top_n]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    parser.add_argument("--interval", default="1H")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--initial-capital", type=float, default=1000)
    parser.add_argument("--search", choices=["preset", "focused", "wide"], default="focused")
    parser.add_argument("--mode", choices=["walk-forward", "static-rank", "both"], default="walk-forward")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.quiet:
        logger.remove()
        db_engine.echo = False

    end = datetime.now()
    start = end - timedelta(days=args.days)
    start_ms = ts_ms(start)
    end_ms = ts_ms(end)

    print(
        f"walk-forward interval={args.interval} range={start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} "
        f"train={args.train_days}d test={args.test_days}d initial={args.initial_capital} search={args.search}"
    )

    if not args.skip_fetch:
        await fetch_data(args.symbols, args.interval, start_ms, end_ms)

    summaries = []
    if args.mode in {"walk-forward", "both"}:
        for symbol in args.symbols:
            summary = walk_forward(
                symbol,
                args.interval,
                start_ms,
                end_ms,
                args.train_days,
                args.test_days,
                args.initial_capital,
                args.search,
            )
            if summary:
                summaries.append(summary)

    if summaries:
        print("\n=== RANKING BY SAMPLE-OUT RETURN ===")
        for row in sorted(summaries, key=lambda item: (item["avg_ret"], -item["max_dd"]), reverse=True):
            print(
                f"{row['symbol']}: avg_ret={row['avg_ret']:.2%} sum_ret={row['sum_ret']:.2%} "
                f"positive={row['positive']}/{row['folds']} max_dd={row['max_dd']:.2%} "
                f"avg_pf={row['avg_pf']:.2f} trades={row['total_trades']} | "
                f"stable {row['stable_count']}/{row['folds']} {format_params(row['stable_params'])}"
            )

    if args.mode in {"static-rank", "both"}:
        for symbol in args.symbols:
            static_rank(
                symbol,
                args.interval,
                start_ms,
                end_ms,
                args.train_days,
                args.test_days,
                args.initial_capital,
                args.search,
                args.top,
            )


if __name__ == "__main__":
    asyncio.run(main())
