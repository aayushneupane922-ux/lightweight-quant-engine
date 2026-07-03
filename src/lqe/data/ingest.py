"""The ingest pipeline (docs/archive/08 §8.7): fetch -> validate -> curated
Parquet -> catalog version. Idempotent: re-ingesting the same or an
overlapping range never duplicates rows (docs/11 §11.4's `write_bars`).
Fails loud and quarantines on a data-quality failure — it never silently
curates bad data.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from lqe.core.errors import DataQualityError
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import MarketDataAdapter
from lqe.data.validate import ValidationReport, validate_bars
from lqe.storage.catalog import Catalog
from lqe.storage.parquet import write_bars


class IngestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    version_id: str
    rows: int
    checksum: str
    report: ValidationReport
    paths: list[str]


def _checksum(paths: list[Path]) -> str:
    hasher = hashlib.sha256()
    for path in sorted(paths):
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def ingest(
    adapter: MarketDataAdapter,
    *,
    exchange: str,
    symbol: Symbol,
    timeframe: Timeframe,
    root: Path,
    catalog: Catalog,
    start: datetime | None = None,
    end: datetime | None = None,
) -> IngestResult:
    bars = list(adapter.stream([symbol], timeframe, start=start, end=end))
    report = validate_bars(bars, timeframe=timeframe)

    if not report.passed:
        quarantine_dir = root / "quarantine" / exchange / symbol / timeframe
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        report_path = quarantine_dir / f"{uuid4()}.json"
        report_path.write_text(report.model_dump_json(indent=2))
        raise DataQualityError(
            f"validation failed for {exchange}/{symbol}/{timeframe}: see {report_path}"
        )

    paths = write_bars(root / "curated" / "ohlcv", bars)
    checksum = _checksum(paths)
    version_id = str(uuid4())
    catalog.record_data_version(
        version_id=version_id,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        path=str(paths[0].parent) if paths else "",
        rows=len(bars),
        checksum=checksum,
        fetched_at=datetime.now(UTC),
        validated=True,
        report=report.model_dump(),
    )
    return IngestResult(
        version_id=version_id,
        rows=len(bars),
        checksum=checksum,
        report=report,
        paths=[str(p) for p in paths],
    )
