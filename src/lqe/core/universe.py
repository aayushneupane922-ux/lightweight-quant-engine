"""`Universe` (V5 M27 "Universe Core", docs/15): groups an already
time-ordered, multi-symbol bar stream into synchronized per-timestamp
cycles, so a multi-instrument backtest or live session can process "every
symbol's bar for this instant" as one deterministic unit.

Purely a function of the bar stream it's handed -- no wall-clock reads, no
network calls -- so replaying the identical stream twice yields identical
cycles (docs/11 determinism). A symbol absent from a cycle is reported in
that cycle's `missing` tuple: no trade happens for it this cycle, and the
caller is expected to log that, but nothing crashes or desyncs the other
symbols' processing.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol


@dataclass(frozen=True)
class UniverseCycle:
    """One synchronized instant across the universe."""

    ts_open: datetime
    bars: tuple[MarketEvent, ...]  # sorted by symbol -- deterministic order
    missing: tuple[Symbol, ...]  # sorted; universe symbols absent this cycle


class Universe:
    """`symbols` is the fixed set this universe tracks (e.g. the 5 spot
    majors). `cycles()` consumes an externally-sorted bar iterator (e.g.
    `CcxtMarketDataAdapter.stream()`, already fixed to interleave symbols
    by `ts_open`, or a merged backtest fixture) and yields one
    `UniverseCycle` per distinct timestamp, in order."""

    def __init__(self, symbols: list[Symbol]) -> None:
        if not symbols:
            raise ValueError("Universe requires at least one symbol")
        self.symbols: tuple[Symbol, ...] = tuple(symbols)
        self.last_seen: dict[Symbol, datetime | None] = dict.fromkeys(self.symbols, None)

    def cycles(self, bars: Iterable[MarketEvent]) -> Iterator[UniverseCycle]:
        current_ts: datetime | None = None
        bucket: list[MarketEvent] = []
        for bar in bars:
            if bar.symbol not in self.symbols:
                raise ValueError(
                    f"bar for {bar.symbol!r} is outside this Universe's symbols {self.symbols}"
                )
            if current_ts is not None and bar.ts_open < current_ts:
                raise ValueError(
                    f"bar stream is not time-ordered: {bar.ts_open} arrived after {current_ts}"
                )
            if current_ts is None:
                current_ts = bar.ts_open
            elif bar.ts_open != current_ts:
                yield self._finish_cycle(current_ts, bucket)
                current_ts = bar.ts_open
                bucket = []
            bucket.append(bar)
        if bucket:
            assert current_ts is not None
            yield self._finish_cycle(current_ts, bucket)

    def _finish_cycle(self, ts_open: datetime, bucket: list[MarketEvent]) -> UniverseCycle:
        present = {bar.symbol for bar in bucket}
        missing = tuple(sym for sym in self.symbols if sym not in present)
        for bar in bucket:
            self.last_seen[bar.symbol] = bar.ts_open
        sorted_bars = tuple(sorted(bucket, key=lambda b: b.symbol))
        return UniverseCycle(ts_open=ts_open, bars=sorted_bars, missing=missing)
