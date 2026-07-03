"""`lqe validate` end-to-end (v0.1's honest loop): ingest -> bundle ->
validate, writing a tearsheet and recording the run in the registry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lqe.analytics.registry import ExperimentRegistry
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


CLEAN_CSV = "ts_open,open,high,low,close,volume\n" + "\n".join(_row(i) for i in range(300)) + "\n"


def test_cli_validate_runs_end_to_end_and_records_the_experiment(tmp_path: Path) -> None:
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(CLEAN_CSV, encoding="utf-8")
    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)

    adapter = CsvReplayAdapter(csv_path, exchange="binance", symbol="BTC-USDT", timeframe="1m")
    with Catalog(root / "catalog.duckdb") as catalog:
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
        bundle_id="cli-validate-bundle",
        exchange="binance",
        symbols=["BTC-USDT"],
        timeframe="1m",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        seed=1,
        source_versions=[result.version_id],
    )

    tearsheet_path = tmp_path / "tearsheet.md"
    exit_code = main(
        [
            "validate",
            "--bundle", "cli-validate-bundle",
            "--root", str(root),
            "--symbol", "BTC-USDT",
            "--fast", "3",
            "--slow", "10",
            "--n-folds", "2",
            "--random-control-reps", "2",
            "--tearsheet-out", str(tearsheet_path),
        ]
    )
    assert exit_code == 0
    assert tearsheet_path.exists()
    sheet = tearsheet_path.read_text(encoding="utf-8")
    assert "no profitability is claimed" in sheet.lower()
    assert "Verdict:" in sheet

    with Catalog(root / "catalog.duckdb") as catalog:
        registry = ExperimentRegistry(catalog)
        experiments = registry.experiments()
    assert len(experiments) == 1
    assert experiments[0]["strategy"] == "trend_ma_cross"
