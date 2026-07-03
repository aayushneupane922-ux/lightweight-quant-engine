"""End-to-end ingest: fetch (CSV fixture) -> validate -> curated Parquet ->
catalog version. Covers docs/10 M2's idempotent-ingest and quarantine-on-
bad-data acceptance tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lqe.core.errors import DataQualityError
from lqe.core.events import MarketEvent
from lqe.core.types import Timeframe
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import IngestResult, ingest
from lqe.storage.catalog import Catalog
from lqe.storage.parquet import read_bars

EXCHANGE = "binance"
SYMBOL = "BTC-USDT"
TIMEFRAME: Timeframe = "1m"

CLEAN_CSV = """ts_open,open,high,low,close,volume
2026-01-01T00:00:00+00:00,100,101,99,100.5,10
2026-01-01T00:01:00+00:00,100.5,102,100,101.5,11
2026-01-01T00:02:00+00:00,101.5,103,101,102.5,12
"""

BAD_CSV = """ts_open,open,high,low,close,volume
2026-01-01T00:00:00+00:00,100,99,101,100.5,10
"""


def _write_csv(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "fixture.csv"
    path.write_text(content, encoding="utf-8")
    return path


def _ingest(tmp_path: Path, root: Path, csv_content: str) -> IngestResult:
    csv_path = _write_csv(tmp_path, csv_content)
    adapter = CsvReplayAdapter(csv_path, exchange=EXCHANGE, symbol=SYMBOL, timeframe=TIMEFRAME)
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        return ingest(
            adapter,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            root=root,
            catalog=catalog,
        )


def _read_curated(root: Path) -> list[MarketEvent]:
    return read_bars(
        root / "curated" / "ohlcv", exchange=EXCHANGE, symbol=SYMBOL, timeframe=TIMEFRAME
    )


def test_ingest_writes_curated_bars_and_catalog_version(tmp_path: Path) -> None:
    root = tmp_path / "data"
    result = _ingest(tmp_path, root, CLEAN_CSV)

    assert result.rows == 3
    assert result.report.passed is True

    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        versions = catalog.data_versions()
    assert len(versions) == 1
    assert versions[0]["rows"] == 3
    assert len(_read_curated(root)) == 3


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "data"
    checksum_a = _ingest(tmp_path, root, CLEAN_CSV).checksum
    checksum_b = _ingest(tmp_path, root, CLEAN_CSV).checksum

    assert checksum_a == checksum_b  # same bytes on disk, not duplicated
    assert len(_read_curated(root)) == 3  # not 6


def test_ingest_quarantines_bad_data_instead_of_curating_it(tmp_path: Path) -> None:
    root = tmp_path / "data"
    with pytest.raises(DataQualityError):
        _ingest(tmp_path, root, BAD_CSV)

    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        assert catalog.data_versions() == []

    quarantine_dir = root / "quarantine" / EXCHANGE / SYMBOL / TIMEFRAME
    assert quarantine_dir.exists()
    assert list(quarantine_dir.glob("*.json"))
    assert not (root / "curated" / "ohlcv").exists()
