"""Clock protocol + implementations (docs/11 §11.2).

Time is always injected. Nothing in a decision path reads the wall clock
directly — `ReplayClock` drives backtests/trials/validation deterministically
from a fixed timestamp sequence; `WallclockClock` drives the live paper
daemon from real time.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def advance(self) -> datetime | None: ...


class ReplayClock:
    """Deterministic playback over a fixed, ordered timestamp sequence."""

    def __init__(self, timestamps: Sequence[datetime]) -> None:
        ordered = list(timestamps)
        if ordered != sorted(ordered):
            raise ValueError("ReplayClock timestamps must be non-decreasing")
        self._timestamps = ordered
        self._index = -1

    def now(self) -> datetime:
        if self._index < 0:
            raise RuntimeError("ReplayClock.now() called before the first advance()")
        return self._timestamps[self._index]

    def advance(self) -> datetime | None:
        if self._index + 1 >= len(self._timestamps):
            return None
        self._index += 1
        return self._timestamps[self._index]


class WallclockClock:
    """Real-time clock for the live paper daemon."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def advance(self) -> datetime | None:
        return self.now()
