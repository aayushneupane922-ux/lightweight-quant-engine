"""Partitioned + flat Parquet storage for funding-rate history (docs/14 v4
sleeve F). Mirrors `storage/parquet.py`'s idempotent partitioned-write
pattern exactly (same de-dup-by-timestamp merge, same Hive-style directory
layout), but with `FundingRateEvent`'s own (smaller) schema -- there's no
OHLCV here, just a settlement timestamp and a rate.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from lqe.core.events import FundingRateEvent
from lqe.core.types import Symbol

SCHEMA = pa.schema(
    [
        ("ts", pa.timestamp("us", tz="UTC")),
        ("exchange", pa.string()),
        ("symbol", pa.string()),
        ("rate", pa.float64()),
        ("source_version", pa.string()),
    ]
)


def partition_dir(root: Path, *, exchange: str, symbol: Symbol, year: int, month: int) -> Path:
    return (
        root
        / f"exchange={exchange}"
        / f"symbol={symbol}"
        / f"year={year}"
        / f"month={month:02d}"
    )


def _rate_to_row(rate: FundingRateEvent) -> dict[str, object]:
    return {
        "ts": rate.ts,
        "exchange": rate.exchange,
        "symbol": rate.symbol,
        "rate": rate.rate,
        "source_version": rate.source_version,
    }


def _row_to_rate(row: dict[str, object]) -> FundingRateEvent:
    return FundingRateEvent(
        exchange=str(row["exchange"]),
        symbol=str(row["symbol"]),
        ts=row["ts"],  # type: ignore[arg-type]
        rate=float(row["rate"]),  # type: ignore[arg-type]
        source_version=str(row["source_version"]),
    )


def write_funding_rates(root: Path, rates: Sequence[FundingRateEvent]) -> list[Path]:
    """Merge `rates` into their monthly partitions, de-duplicating by `ts`
    (idempotent: re-writing the same or overlapping range never grows a
    partition file, same guarantee as `parquet.write_bars`)."""
    if not rates:
        return []
    by_partition: dict[tuple[str, Symbol, int, int], list[FundingRateEvent]] = {}
    for rate in rates:
        key = (rate.exchange, rate.symbol, rate.ts.year, rate.ts.month)
        by_partition.setdefault(key, []).append(rate)

    written: list[Path] = []
    for (exchange, symbol, year, month), group in by_partition.items():
        directory = partition_dir(root, exchange=exchange, symbol=symbol, year=year, month=month)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "part-0000.parquet"

        rows_by_ts: dict[datetime, dict[str, object]] = {}
        if path.exists():
            for row in pq.ParquetFile(path).read().to_pylist():
                rows_by_ts[row["ts"]] = row
        for rate in group:
            rows_by_ts[rate.ts] = _rate_to_row(rate)

        ordered_rows = [rows_by_ts[ts] for ts in sorted(rows_by_ts)]
        pq.write_table(pa.Table.from_pylist(ordered_rows, schema=SCHEMA), path)
        written.append(path)
    return written


def read_funding_rates(
    root: Path,
    *,
    exchange: str,
    symbol: Symbol,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[FundingRateEvent]:
    base = root / f"exchange={exchange}" / f"symbol={symbol}"
    if not base.exists():
        return []
    rates: list[FundingRateEvent] = []
    for path in sorted(base.rglob("*.parquet")):
        for row in pq.ParquetFile(path).read().to_pylist():
            ts = row["ts"]
            if start is not None and ts < start:
                continue
            if end is not None and ts >= end:
                continue
            rates.append(_row_to_rate(row))
    rates.sort(key=lambda r: r.ts)
    return rates
