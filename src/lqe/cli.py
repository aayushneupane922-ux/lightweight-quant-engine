"""`lqe` command-line entry point. Thin wiring only — no decision logic lives
here; every subcommand just builds an adapter and calls into `lqe.data`/
`lqe.storage` (docs/10 M2: `cli lqe ingest`).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
