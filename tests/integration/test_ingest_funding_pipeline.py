"""End-to-end funding-rate ingest: fetch (fake ccxt exchange) -> validate ->
curated Parquet -> catalog version, mirroring `test_ingest_pipeline.py`'s
OHLCV acceptance tests exactly (docs/14 §5 v4: "validated like all data").
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lqe.core.errors import DataQualityError
from lqe.data.funding_adapter import CcxtFundingRateAdapter
from lqe.data.ingest import (
    FUNDING_TIMEFRAME_SENTINEL,
    IngestFundingResult,
    ingest_funding_rates,
)
from lqe.storage.catalog import Catalog
from lqe.storage.parquet_funding import read_funding_rates

EXCHANGE = "binance"
SYMBOL = "BTC-USDT-PERP"


class _FakeExchange:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetch_funding_rate_history(
        self, native_symbol: str, since: int | None = None
    ) -> list[dict[str, object]]:
        return self._rows


def _row(hour: int, rate: float) -> dict[str, object]:
    ts = datetime(2026, 1, 1, hour, tzinfo=UTC)
    return {"timestamp": int(ts.timestamp() * 1000), "fundingRate": rate}


CLEAN_ROWS = [_row(0, 0.0001), _row(8, 0.0002), _row(16, -0.0001)]
BAD_ROWS = [_row(0, 0.5)]  # implausible 50%/interval rate


def _ingest(tmp_path: Path, root: Path, rows: list[dict[str, object]]) -> IngestFundingResult:
    adapter = CcxtFundingRateAdapter(EXCHANGE, exchange=_FakeExchange(rows))
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        return ingest_funding_rates(
            adapter, exchange=EXCHANGE, symbol=SYMBOL, root=root, catalog=catalog,
        )


def test_ingest_writes_curated_funding_rates_and_catalog_version(tmp_path: Path) -> None:
    root = tmp_path / "data"
    result = _ingest(tmp_path, root, CLEAN_ROWS)

    assert result.rows == 3
    assert result.report.passed is True

    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        versions = catalog.data_versions()
    assert len(versions) == 1
    assert versions[0]["timeframe"] == FUNDING_TIMEFRAME_SENTINEL
    assert versions[0]["rows"] == 3
    read = read_funding_rates(root / "curated" / "funding", exchange=EXCHANGE, symbol=SYMBOL)
    assert len(read) == 3


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "data"
    checksum_a = _ingest(tmp_path, root, CLEAN_ROWS).checksum
    checksum_b = _ingest(tmp_path, root, CLEAN_ROWS).checksum

    assert checksum_a == checksum_b
    read = read_funding_rates(root / "curated" / "funding", exchange=EXCHANGE, symbol=SYMBOL)
    assert len(read) == 3  # not 6


def test_ingest_quarantines_implausible_rates_instead_of_curating_them(tmp_path: Path) -> None:
    root = tmp_path / "data"
    with pytest.raises(DataQualityError):
        _ingest(tmp_path, root, BAD_ROWS)

    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        assert catalog.data_versions() == []

    quarantine_dir = root / "quarantine" / EXCHANGE / SYMBOL / FUNDING_TIMEFRAME_SENTINEL
    assert quarantine_dir.exists()
    assert list(quarantine_dir.glob("*.json"))
    assert not (root / "curated" / "funding").exists()
