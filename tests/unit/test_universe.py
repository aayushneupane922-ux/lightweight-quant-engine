"""Survivorship-safe ranked universe (docs/10 M11, docs/03 §3.6):
membership is as-of-date correct (dead names included while they were
alive, future listings excluded) and the ranking is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lqe.core.types import SymbolRecord
from lqe.portfolio.universe import RankedUniverse


def _rec(canonical: str, listed: int, delisted: int | None = None) -> SymbolRecord:
    return SymbolRecord(
        canonical=canonical, exchange="binance", native_symbol=canonical,
        base=canonical.split("-")[0], quote="USDT",
        listed_at=datetime(listed, 1, 1, tzinfo=UTC),
        delisted_at=datetime(delisted, 1, 1, tzinfo=UTC) if delisted else None,
    )


_UNIVERSE = RankedUniverse.from_records([
    _rec("BTC-USDT", 2020),
    _rec("ETH-USDT", 2021),
    _rec("DEAD-USDT", 2020, 2022),  # delisted at 2022
    _rec("NEW-USDT", 2023),  # listed later
])


def test_membership_is_as_of_correct() -> None:
    as_of = datetime(2021, 6, 1, tzinfo=UTC)
    members = {r.canonical for r in _UNIVERSE.tradeable_at(as_of)}
    assert members == {"BTC-USDT", "ETH-USDT", "DEAD-USDT"}  # NEW not listed, DEAD still alive


def test_delisted_name_leaves_and_new_name_joins() -> None:
    later = datetime(2023, 6, 1, tzinfo=UTC)
    members = {r.canonical for r in _UNIVERSE.tradeable_at(later)}
    assert members == {"BTC-USDT", "ETH-USDT", "NEW-USDT"}  # DEAD delisted, NEW listed


def test_ranking_includes_a_dead_name_that_was_alive_then() -> None:
    # the survivorship-safe point: DEAD outranks the survivors while it was
    # tradeable — dropping it would inflate the survivors' apparent edge
    as_of = datetime(2021, 6, 1, tzinfo=UTC)
    factors = {"BTC-USDT": 0.5, "ETH-USDT": 0.3, "DEAD-USDT": 0.99}
    ranked = _UNIVERSE.rank(as_of=as_of, factor_fn=lambda s: factors[s], top_n=2)
    assert ranked == ["DEAD-USDT", "BTC-USDT"]


def test_ranking_is_deterministic_with_stable_tiebreak() -> None:
    as_of = datetime(2022, 6, 1, tzinfo=UTC)  # DEAD delisted at 2022-01 -> excluded
    ranked = _UNIVERSE.rank(as_of=as_of, factor_fn=lambda s: 0.5, top_n=5)
    assert ranked == ["BTC-USDT", "ETH-USDT"]  # all-tie -> canonical order, deterministic
    assert ranked == _UNIVERSE.rank(as_of=as_of, factor_fn=lambda s: 0.5, top_n=5)
