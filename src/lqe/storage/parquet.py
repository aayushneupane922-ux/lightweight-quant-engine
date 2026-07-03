"""Partitioned + flat Parquet storage for OHLCV bars (docs/11 §11.4, docs/archive/08 §8.3).

Curated bars are stored `float64` (matching the documented curated schema
exactly) — this is deliberately different from the `Decimal` used in the
in-memory `MarketEvent` payload (docs/11 §11.0's Decimal rule targets money/
accounting values in the decision path, not raw stored market ticks).
`write_bars` is idempotent: writing the same bars twice, or overlapping
ranges, de-duplicates by `ts_open` and never grows a partition file.

Reads use `pq.ParquetFile(path).read()`, not `pq.read_table(path)`: the
partition directories are named `exchange=.../symbol=.../...` (Hive-style),
and `read_table` walks ancestor directories to infer partition columns —
which then conflicts with the same-named columns already embedded in the
file (a real vs. dictionary-encoded `exchange` field, for example).
`ParquetFile` reads only the file's own schema, no ancestor inference.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe

SCHEMA = pa.schema(
    [
        ("ts_open", pa.timestamp("us", tz="UTC")),
        ("exchange", pa.string()),
        ("symbol", pa.string()),
        ("timeframe", pa.string()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
        ("trades", pa.int64()),
        ("source_version", pa.string()),
        ("is_gap_filled", pa.bool_()),
    ]
)


def partition_dir(
    root: Path, *, exchange: str, symbol: Symbol, timeframe: Timeframe, year: int, month: int
) -> Path:
    return (
        root
        / f"exchange={exchange}"
        / f"symbol={symbol}"
        / f"timeframe={timeframe}"
        / f"year={year}"
        / f"month={month:02d}"
    )


def _bar_to_row(bar: MarketEvent, *, is_gap_filled: bool = False) -> dict[str, object]:
    return {
        "ts_open": bar.ts_open,
        "exchange": bar.exchange,
        "symbol": bar.symbol,
        "timeframe": bar.timeframe,
        "open": float(bar.o),
        "high": float(bar.h),
        "low": float(bar.l),
        "close": float(bar.c),
        "volume": bar.v,
        "trades": None,
        "source_version": bar.source_version,
        "is_gap_filled": is_gap_filled,
    }


def _row_to_bar(row: dict[str, object]) -> MarketEvent:
    return MarketEvent(
        exchange=str(row["exchange"]),
        symbol=str(row["symbol"]),
        timeframe=row["timeframe"],  # type: ignore[arg-type]
        ts_open=row["ts_open"],  # type: ignore[arg-type]
        o=Decimal(str(row["open"])),
        h=Decimal(str(row["high"])),
        l=Decimal(str(row["low"])),
        c=Decimal(str(row["close"])),
        v=float(row["volume"]),  # type: ignore[arg-type]
        source_version=str(row["source_version"]),
    )


def write_flat(path: Path, bars: Sequence[MarketEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_bar_to_row(bar) for bar in sorted(bars, key=lambda b: (b.symbol, b.ts_open))]
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    pq.write_table(table, path)


def read_flat(path: Path) -> list[MarketEvent]:
    return [_row_to_bar(row) for row in pq.ParquetFile(path).read().to_pylist()]


def write_bars(root: Path, bars: Sequence[MarketEvent]) -> list[Path]:
    """Merge `bars` into their monthly partitions, de-duplicating by `ts_open`."""
    if not bars:
        return []
    by_partition: dict[tuple[str, Symbol, Timeframe, int, int], list[MarketEvent]] = {}
    for bar in bars:
        key = (bar.exchange, bar.symbol, bar.timeframe, bar.ts_open.year, bar.ts_open.month)
        by_partition.setdefault(key, []).append(bar)

    written: list[Path] = []
    for (exchange, symbol, timeframe, year, month), group in by_partition.items():
        directory = partition_dir(
            root, exchange=exchange, symbol=symbol, timeframe=timeframe, year=year, month=month
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "part-0000.parquet"

        rows_by_ts: dict[datetime, dict[str, object]] = {}
        if path.exists():
            for row in pq.ParquetFile(path).read().to_pylist():
                rows_by_ts[row["ts_open"]] = row
        for bar in group:
            rows_by_ts[bar.ts_open] = _bar_to_row(bar)

        ordered_rows = [rows_by_ts[ts] for ts in sorted(rows_by_ts)]
        pq.write_table(pa.Table.from_pylist(ordered_rows, schema=SCHEMA), path)
        written.append(path)
    return written


def read_bars(
    root: Path,
    *,
    exchange: str,
    symbol: Symbol,
    timeframe: Timeframe,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[MarketEvent]:
    base = root / f"exchange={exchange}" / f"symbol={symbol}" / f"timeframe={timeframe}"
    if not base.exists():
        return []
    bars: list[MarketEvent] = []
    for path in sorted(base.rglob("*.parquet")):
        for row in pq.ParquetFile(path).read().to_pylist():
            ts_open = row["ts_open"]
            if start is not None and ts_open < start:
                continue
            if end is not None and ts_open >= end:
                continue
            bars.append(_row_to_bar(row))
    bars.sort(key=lambda b: b.ts_open)
    return bars
