"""CSV-backed `MarketDataAdapter` for deterministic replay (docs/06 §6.3).

Expects a CSV with columns `ts_open,open,high,low,close,volume`, ISO-8601
UTC timestamps, pre-sorted ascending by `ts_open` — the adapter streams rows
in file order and does not re-sort, so an unsorted input file is a bug in
the fixture, not something this adapter silently fixes.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import DataCapabilities


class CsvReplayAdapter:
    def __init__(
        self,
        path: str | Path,
        *,
        exchange: str,
        symbol: Symbol,
        timeframe: Timeframe,
        source_version: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._exchange = exchange
        self._symbol = symbol
        self._timeframe = timeframe
        self._source_version = source_version or f"csv:{self._path.name}"

    def capabilities(self) -> DataCapabilities:
        return DataCapabilities(bars=True)

    def stream(
        self,
        symbols: list[Symbol],
        tf: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[MarketEvent]:
        if self._symbol not in symbols or tf != self._timeframe:
            return
        with self._path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ts_open = datetime.fromisoformat(row["ts_open"])
                if ts_open.tzinfo is None:
                    ts_open = ts_open.replace(tzinfo=UTC)
                if start is not None and ts_open < start:
                    continue
                if end is not None and ts_open >= end:
                    continue
                yield MarketEvent(
                    exchange=self._exchange,
                    symbol=self._symbol,
                    timeframe=tf,
                    ts_open=ts_open,
                    o=Decimal(row["open"]),
                    h=Decimal(row["high"]),
                    l=Decimal(row["low"]),
                    c=Decimal(row["close"]),
                    v=float(row["volume"]),
                    source_version=self._source_version,
                )
