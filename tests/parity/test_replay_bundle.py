"""A replay bundle is a frozen, checksummed set of bars (docs/archive/08
§8.5): building it twice from the same curated data produces the same
bytes/checksum, and tampering with a frozen bundle is detected on load.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lqe.core.errors import DataQualityError
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import ingest
from lqe.storage.catalog import Catalog
from lqe.storage.replay_bundle import build_bundle, load_bundle

CLEAN_CSV = """ts_open,open,high,low,close,volume
2026-01-01T00:00:00+00:00,100,101,99,100.5,10
2026-01-01T00:01:00+00:00,100.5,102,100,101.5,11
2026-01-01T00:02:00+00:00,101.5,103,101,102.5,12
"""


def _ingested_root(tmp_path: Path) -> tuple[Path, str]:
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(CLEAN_CSV, encoding="utf-8")
    adapter = CsvReplayAdapter(csv_path, exchange="binance", symbol="BTC-USDT", timeframe="1m")
    root = tmp_path / "data"
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        result = ingest(
            adapter,
            exchange="binance",
            symbol="BTC-USDT",
            timeframe="1m",
            root=root,
            catalog=catalog,
        )
    return root, result.version_id


def test_replay_bundle_round_trips_and_is_reproducible(tmp_path: Path) -> None:
    root, version_id = _ingested_root(tmp_path)

    bundle_a = build_bundle(
        root, bundle_id="bundle-1", exchange="binance", symbols=["BTC-USDT"], timeframe="1m",
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 2, tzinfo=UTC),
        seed=42, source_versions=[version_id],
    )
    loaded_bundle, bars = load_bundle(root, "bundle-1")

    assert loaded_bundle.checksum == bundle_a.checksum
    assert len(bars) == 3
    assert [b.c for b in bars] == sorted(b.c for b in bars)  # sorted by ts_open ascending


def test_tampered_bundle_fails_checksum_on_load(tmp_path: Path) -> None:
    root, version_id = _ingested_root(tmp_path)
    build_bundle(
        root, bundle_id="bundle-2", exchange="binance", symbols=["BTC-USDT"], timeframe="1m",
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 2, tzinfo=UTC),
        seed=1, source_versions=[version_id],
    )
    events_path = root / "replay" / "bundle-2" / "events.parquet"
    with events_path.open("ab") as fh:
        fh.write(b"\x00\x00\x00")

    with pytest.raises(DataQualityError):
        load_bundle(root, "bundle-2")
