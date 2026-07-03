"""`lqe` command-line entry point. Thin wiring only — no decision logic lives
here; every subcommand just builds an adapter and calls into `lqe.data`/
`lqe.storage` (docs/10 M2: `cli lqe ingest`).
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from lqe.analytics.metrics import compute_metrics
from lqe.analytics.registry import ExperimentRegistry
from lqe.analytics.tearsheet import render_tearsheet
from lqe.autonomy.promotion_gate import PromotionGate
from lqe.autonomy.validator import PromotionCandidate, Validator
from lqe.backtest.runner import run_backtest
from lqe.data.base import MarketDataAdapter
from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import ingest
from lqe.models.base import Strategy
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.storage.catalog import Catalog
from lqe.storage.replay_bundle import load_bundle

STRATEGIES = {"trend_ma_cross"}


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        )
        return completed.stdout.strip()
    except Exception:
        return "unknown"


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _cmd_ingest(args: argparse.Namespace) -> int:
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    adapter: MarketDataAdapter
    if args.adapter == "ccxt":
        adapter = CcxtMarketDataAdapter(args.exchange)
    else:
        adapter = CsvReplayAdapter(
            args.csv_path, exchange=args.exchange, symbol=args.symbol, timeframe=args.timeframe
        )

    with Catalog(root / args.catalog) as catalog:
        result = ingest(
            adapter,
            exchange=args.exchange,
            symbol=args.symbol,
            timeframe=args.timeframe,
            root=root,
            catalog=catalog,
            start=_parse_ts(args.start),
            end=_parse_ts(args.end),
        )

    print(
        f"ingested {result.rows} bars -> version {result.version_id} "
        f"(checksum {result.checksum[:12]}...)"
    )
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    root = Path(args.root)
    bundle, bars = load_bundle(root, args.bundle)
    symbol_bars = [bar for bar in bars if bar.symbol == args.symbol]
    if not symbol_bars:
        print(f"no bars for symbol {args.symbol!r} in bundle {args.bundle!r}")
        return 1

    strategy: Strategy = TrendMaCross(symbol=args.symbol, fast=args.fast, slow=args.slow)
    session = run_backtest(
        run_id=f"backtest:{args.bundle}:{strategy.name}",
        symbol=args.symbol,
        bars=symbol_bars,
        strategy=strategy,
        starting_cash=Decimal(str(args.starting_cash)),
        slippage_bps=args.slippage_bps,
        commission_bps=args.commission_bps,
    )

    final_equity = session.accounting.equity({args.symbol: symbol_bars[-1].c})
    print(f"bundle {bundle.bundle_id} ({len(symbol_bars)} bars) -> strategy {strategy.name}")
    print(f"starting cash: {args.starting_cash}  final equity: {final_equity}")
    print(f"audit hash-chain verifies: {session.engine.audit.verify()}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root)
    bundle, bars = load_bundle(root, args.bundle)
    symbol_bars = [bar for bar in bars if bar.symbol == args.symbol]
    if not symbol_bars:
        print(f"no bars for symbol {args.symbol!r} in bundle {args.bundle!r}")
        return 1

    starting_cash = Decimal(str(args.starting_cash))

    def _strategy_factory() -> Strategy:
        return TrendMaCross(symbol=args.symbol, fast=args.fast, slow=args.slow)

    candidate = PromotionCandidate(
        candidate_id=f"{args.bundle}:{args.strategy}:{args.fast}-{args.slow}",
        model_id=args.strategy,
        params={"fast": args.fast, "slow": args.slow},
        book="sandbox",
        hypo_id=args.hypo_id,
        study_id=args.study_id,
        data_version=bundle.bundle_id,
        seed=bundle.seed,
        n_trials_context=args.n_trials_context,
    )

    validator = Validator(n_folds=args.n_folds, random_control_reps=args.random_control_reps)
    result = validator.validate(
        candidate,
        bars=symbol_bars,
        symbol=args.symbol,
        strategy_factory=_strategy_factory,
        starting_cash=starting_cash,
    )
    gate_result = PromotionGate().check(candidate, result, n_periods=len(symbol_bars))

    full_session = run_backtest(
        run_id=f"validate-report:{candidate.candidate_id}",
        symbol=args.symbol,
        bars=symbol_bars,
        strategy=_strategy_factory(),
        starting_cash=starting_cash,
        commission_bps=args.commission_bps,
    )
    metrics = compute_metrics(
        equity_curve=full_session.equity_curve,
        trade_pnls=full_session.trade_pnls,
        trade_notionals=full_session.trade_notionals,
        periods_per_year=365 * 24 * 60,
    )
    sheet = render_tearsheet(
        model_id=args.strategy,
        metrics=metrics,
        gate_result=gate_result,
        cost_bps_used=args.commission_bps,
    )

    with Catalog(root / args.catalog) as catalog:
        registry = ExperimentRegistry(catalog)
        registry.record_experiment(
            run_id=f"validate:{candidate.candidate_id}",
            mode="backtest",
            book="sandbox",
            strategy=args.strategy,
            params=candidate.params,
            data_version=bundle.bundle_id,
            git_sha=_git_sha(),
            seed=bundle.seed,
            date_start=symbol_bars[0].ts_open,
            date_end=symbol_bars[-1].ts_open,
            split="full",
            sharpe=metrics.sharpe,
            dsr=gate_result.dsr,
            pbo=gate_result.pbo,
            max_dd=metrics.max_drawdown,
            turnover=metrics.turnover,
            n_trades=metrics.n_trades,
            cost_bps=args.commission_bps,
            passed_gate=gate_result.verdict == "PASS",
            created_at=datetime.now(UTC),
        )

    print(sheet)
    if args.tearsheet_out:
        Path(args.tearsheet_out).write_text(sheet, encoding="utf-8")
        print(f"tearsheet written to {args.tearsheet_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lqe")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Fetch, validate, and curate OHLCV bars.")
    ingest_parser.add_argument("--adapter", choices=["ccxt", "csv"], required=True)
    ingest_parser.add_argument("--exchange", required=True)
    ingest_parser.add_argument(
        "--symbol", required=True, help="Canonical BASE-QUOTE, e.g. BTC-USDT"
    )
    ingest_parser.add_argument("--timeframe", required=True)
    ingest_parser.add_argument("--root", default="data", help="Storage root (default: ./data)")
    ingest_parser.add_argument(
        "--catalog", default="catalog.duckdb", help="Catalog path, relative to root"
    )
    ingest_parser.add_argument("--csv-path", help="Required when --adapter csv")
    ingest_parser.add_argument("--start", default=None, help="ISO-8601 UTC, inclusive")
    ingest_parser.add_argument("--end", default=None, help="ISO-8601 UTC, exclusive")
    ingest_parser.set_defaults(func=_cmd_ingest)

    backtest_parser = subparsers.add_parser("backtest", help="Run a deterministic backtest.")
    backtest_parser.add_argument("--bundle", required=True, help="Replay bundle id")
    backtest_parser.add_argument("--root", default="data", help="Storage root (default: ./data)")
    backtest_parser.add_argument(
        "--symbol", required=True, help="Canonical BASE-QUOTE, e.g. BTC-USDT"
    )
    backtest_parser.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default="trend_ma_cross"
    )
    backtest_parser.add_argument("--fast", type=int, default=12)
    backtest_parser.add_argument("--slow", type=int, default=48)
    backtest_parser.add_argument("--starting-cash", type=str, default="10000")
    backtest_parser.add_argument("--slippage-bps", type=float, default=5.0)
    backtest_parser.add_argument("--commission-bps", type=float, default=10.0)
    backtest_parser.set_defaults(func=_cmd_backtest)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Run the promotion gate (walk-forward + DSR/PBO + cost sweep + benchmarks).",
    )
    validate_parser.add_argument("--bundle", required=True, help="Replay bundle id")
    validate_parser.add_argument("--root", default="data", help="Storage root (default: ./data)")
    validate_parser.add_argument(
        "--symbol", required=True, help="Canonical BASE-QUOTE, e.g. BTC-USDT"
    )
    validate_parser.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default="trend_ma_cross"
    )
    validate_parser.add_argument("--fast", type=int, default=12)
    validate_parser.add_argument("--slow", type=int, default=48)
    validate_parser.add_argument("--starting-cash", type=str, default="10000")
    validate_parser.add_argument("--commission-bps", type=float, default=10.0)
    validate_parser.add_argument("--n-folds", type=int, default=4)
    validate_parser.add_argument("--random-control-reps", type=int, default=20)
    validate_parser.add_argument(
        "--n-trials-context", type=int, default=1, help="Honest trial count feeding DSR/PBO"
    )
    validate_parser.add_argument("--hypo-id", default="manual")
    validate_parser.add_argument("--study-id", default="manual")
    validate_parser.add_argument(
        "--catalog", default="catalog.duckdb", help="Catalog path, relative to root"
    )
    validate_parser.add_argument(
        "--tearsheet-out", default=None, help="Optional file to write the tearsheet to"
    )
    validate_parser.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
