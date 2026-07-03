"""`lqe backtest` end-to-end: ingest a CSV fixture, freeze it into a replay
bundle, then run the CLI subcommand against that bundle (docs/10 M3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lqe.cli import main
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import ingest
from lqe.storage.catalog import Catalog
from lqe.storage.replay_bundle import build_bundle


def _row(i: int) -> str:
    h, m = divmod(i, 60)
    w = i % 20
    ts = f"2026-01-01T{h:02d}:{m:02d}:00+00:00"
    return f"{ts},{100 + w},{101 + w},{99 + w},{100.5 + w},10"


CLEAN_CSV = "ts_open,open,high,low,close,volume\n" + "\n".join(_row(i) for i in range(120)) + "\n"


def test_cli_backtest_runs_end_to_end(tmp_path: Path) -> None:
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(CLEAN_CSV, encoding="utf-8")
    root = tmp_path / "data"

    adapter = CsvReplayAdapter(csv_path, exchange="binance", symbol="BTC-USDT", timeframe="1m")
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        result = ingest(
            adapter,
            exchange="binance",
            symbol="BTC-USDT",
            timeframe="1m",
            root=root,
            catalog=catalog,
        )

    build_bundle(
        root,
        bundle_id="cli-bundle",
        exchange="binance",
        symbols=["BTC-USDT"],
        timeframe="1m",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        seed=1,
        source_versions=[result.version_id],
    )

    exit_code = main(
        [
            "backtest",
            "--bundle",
            "cli-bundle",
            "--root",
            str(root),
            "--symbol",
            "BTC-USDT",
            "--fast",
            "3",
            "--slow",
            "10",
        ]
    )
    assert exit_code == 0
