"""`lqe` command-line entry point. Thin wiring only — no decision logic lives
here; every subcommand just builds an adapter and calls into `lqe.data`/
`lqe.storage` (docs/10 M2: `cli lqe ingest`).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from lqe.data.base import MarketDataAdapter
from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import ingest
from lqe.storage.catalog import Catalog


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
