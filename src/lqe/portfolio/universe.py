"""Survivorship-safe ranked universe (docs/10 M11, docs/03 §3.6).

Factor models rank a *universe* of instruments; ranking today's winners over
a list that silently dropped the delisted losers is the classic
survivorship-bias trap that inflates apparent edge. This builder ranks only
the symbols that were **actually tradeable as of a point in time** — listed
on or before `as_of` and not yet delisted — so a backtest sees the universe
the strategy would really have faced, dead names included.

Deterministic: ties break on the canonical symbol so the ranking is stable
and replayable. No look-ahead — `factor_fn` is the caller's responsibility to
compute from data available at `as_of` only.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from lqe.core.types import Symbol, SymbolRecord

# A factor score for one symbol, computed from data available at the ranking
# time. Higher ranks first.
FactorFn = Callable[[Symbol], float]


@dataclass(frozen=True)
class RankedUniverse:
    records: tuple[SymbolRecord, ...]

    @classmethod
    def from_records(cls, records: Iterable[SymbolRecord]) -> RankedUniverse:
        return cls(records=tuple(records))

    def tradeable_at(self, as_of: datetime) -> list[SymbolRecord]:
        """Symbols that were live as of `as_of`: listed on/before it and not
        delisted on/before it. This is the survivorship-safe membership."""
        out = [
            r for r in self.records
            if r.listed_at <= as_of and (r.delisted_at is None or r.delisted_at > as_of)
        ]
        return sorted(out, key=lambda r: r.canonical)

    def rank(self, *, as_of: datetime, factor_fn: FactorFn, top_n: int) -> list[Symbol]:
        """Top-`top_n` tradeable symbols by descending factor score. Ties
        break on the canonical symbol, so the result is fully deterministic."""
        members = self.tradeable_at(as_of)
        scored = sorted(
            members,
            key=lambda r: (-factor_fn(r.canonical), r.canonical),
        )
        return [r.canonical for r in scored[: max(0, top_n)]]
