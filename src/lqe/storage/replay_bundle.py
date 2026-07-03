"""Frozen, checksummed replay bundles (docs/archive/08 §8.5, docs/11 §11.4).

A bundle freezes an exact set of bars for a date range + symbol set so
backtests/trials/parity tests consume the *exact same bytes* every run.
`load_bundle` re-checksums on every load — a bundle that was edited after
freezing raises rather than silently serving different data.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lqe.core.errors import DataQualityError
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.storage.parquet import read_bars, read_flat, write_flat


class ReplayBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    bundle_id: str
    symbols: list[Symbol]
    timeframe: Timeframe
    start: datetime
    end: datetime
    source_versions: list[str]
    checksum: str
    seed: int


def build_bundle(
    root: Path,
    *,
    bundle_id: str,
    exchange: str,
    symbols: list[Symbol],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    seed: int,
    source_versions: list[str],
) -> ReplayBundle:
    bundle_dir = root / "replay" / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    all_bars: list[MarketEvent] = []
    for symbol in symbols:
        all_bars.extend(
            read_bars(
                root / "curated" / "ohlcv",
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
        )
    all_bars.sort(key=lambda b: (b.symbol, b.ts_open))

    events_path = bundle_dir / "events.parquet"
    write_flat(events_path, all_bars)
    checksum = hashlib.sha256(events_path.read_bytes()).hexdigest()

    bundle = ReplayBundle(
        bundle_id=bundle_id,
        symbols=symbols,
        timeframe=timeframe,
        start=start,
        end=end,
        source_versions=source_versions,
        checksum=checksum,
        seed=seed,
    )
    (bundle_dir / "bundle.json").write_text(bundle.model_dump_json(indent=2))
    return bundle


def load_bundle(root: Path, bundle_id: str) -> tuple[ReplayBundle, list[MarketEvent]]:
    bundle_dir = root / "replay" / bundle_id
    manifest = bundle_dir / "bundle.json"
    if not manifest.exists():
        raise DataQualityError(
            f"replay bundle {bundle_id!r} not found under {root / 'replay'} "
            f"— run `lqe ingest` then build a bundle first"
        )
    bundle = ReplayBundle.model_validate_json(manifest.read_text())

    events_path = bundle_dir / "events.parquet"
    actual_checksum = hashlib.sha256(events_path.read_bytes()).hexdigest()
    if actual_checksum != bundle.checksum:
        raise DataQualityError(
            f"replay bundle {bundle_id!r} checksum mismatch — data changed after freezing"
        )
    return bundle, read_flat(events_path)
