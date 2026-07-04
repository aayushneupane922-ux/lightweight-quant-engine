"""Perf phase 3d: `StatsmodelsPairsAdapter` gained a `refit_every` schedule
(same pattern as arch=10/hmm=20/supervised=25) so the OLS hedge-ratio fit
-- the expensive part -- can be cached between refits instead of re-run
every single bar.

The default stays `refit_every=1`, which is byte-identical to the previous
always-refit behavior; the scaled catalog still constructs pairs models
with that default, so nothing in the shipped catalog changes signal output.
Bumping the catalog to a sparser schedule is a deliberate, reviewable
one-line config change, not part of this perf work.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.util import find_spec

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent

pytestmark = pytest.mark.skipif(
    find_spec("statsmodels") is None, reason="requires the optional 'models' extra"
)

SYMBOL = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)
CTX = Context(symbol=SYMBOL, position_qty=Decimal("0"))
N = 260


def _series() -> tuple[list[float], list[MarketEvent]]:
    hedge = [50.0 + 0.3 * math.sin(i / 17) + 0.02 * i for i in range(N)]
    bars = []
    for i, h in enumerate(hedge):
        # cointegrated-ish: tracks 2x hedge plus a wandering spread
        c = round(2 * h + 1.5 * math.sin(i / 7), 4)
        bars.append(
            MarketEvent(
                exchange="x", symbol=SYMBOL, timeframe="1m",
                ts_open=START + timedelta(minutes=i),
                o=Decimal(str(c)), h=Decimal(str(c + 0.5)), l=Decimal(str(c - 0.5)),
                c=Decimal(str(c)), v=1.0, source_version="t",
            )
        )
    return hedge, bars


def _run(refit_every: int, ols_calls: list[int] | None = None) -> list[tuple[int, str]]:
    from lqe.models.adapters.statsmodels_pairs_adapter import StatsmodelsPairsAdapter

    hedge, bars = _series()
    adapter = StatsmodelsPairsAdapter(
        symbol=SYMBOL, name="pairs_t", hedge_closes=hedge, window=40, refit_every=refit_every
    )
    if ols_calls is not None:
        real_ols = adapter._sm.OLS  # type: ignore[attr-defined]

        def counting_ols(*args: object, **kwargs: object) -> object:
            ols_calls.append(1)
            return real_ols(*args, **kwargs)

        add_constant = adapter._sm.add_constant  # type: ignore[attr-defined]
        adapter._sm = type("SM", (), {"OLS": counting_ols, "add_constant": add_constant})
    adapter.on_start(CTX)
    out: list[tuple[int, str]] = []
    for i, bar in enumerate(bars):
        for sig in adapter.on_market(bar, CTX):
            out.append((i, sig.direction))
    return out


def test_default_refit_every_1_is_the_old_per_bar_behavior() -> None:
    from lqe.models.adapters.statsmodels_pairs_adapter import StatsmodelsPairsAdapter

    hedge, _ = _series()
    adapter = StatsmodelsPairsAdapter(symbol=SYMBOL, name="p", hedge_closes=hedge)
    assert adapter.params["refit_every"] == 1
    calls: list[int] = []
    _run(1, calls)
    assert sum(calls) == N - 40 + 1  # one OLS per bar once the window fills


def test_sparser_refit_fits_only_on_schedule_and_is_deterministic() -> None:
    calls: list[int] = []
    signals_a = _run(10, calls)
    active_bars = N - 40 + 1
    assert sum(calls) == math.ceil(active_bars / 10)
    assert signals_a == _run(10)  # run-twice determinism, same config

def test_sparser_refit_still_produces_signals() -> None:
    assert len(_run(10)) > 0
