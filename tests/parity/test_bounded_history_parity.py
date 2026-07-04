"""Perf phase 3c: adapters keep a bounded raw history (ADAPTER_HISTORY_CAP)
so per-bar indicator recompute stays O(cap) instead of O(session length).

Parity contract: the cap must be observationally invisible -- an adapter
run with a small cap emits the EXACT same signal sequence as one with an
effectively-unbounded history, over a series long enough to trigger
several trims. Window-bounded (FIR-style) presets are bit-identical by
construction; recursive ones (EMA/Wilder inside macd/rsi/adx/ou) carry a
truncated-tail influence of (1-alpha)^(cap-window) -- far below float64
resolution at the caps used here. If this test ever fails, RAISE the cap
in src/lqe/constants.py; do not weaken the test.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import lqe.models.adapters.indicator_rule_adapter as ira
from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter

START = datetime(2026, 1, 1, tzinfo=UTC)
CTX = Context(symbol="BTC-USDT", position_qty=Decimal("0"))


def _bars(n: int) -> list[MarketEvent]:
    """A deterministic wandering series with real trends and reversals so
    presets actually fire transitions (a flat line would trivially pass)."""
    bars = []
    price = 100.0
    for i in range(n):
        price += 0.6 * math.sin(i / 37) + 0.25 * math.sin(i / 11) + 0.05 * math.cos(i / 3)
        o = round(price - 0.1, 4)
        c = round(price, 4)
        bars.append(
            MarketEvent(
                exchange="x", symbol="BTC-USDT", timeframe="1m",
                ts_open=START + timedelta(minutes=i),
                o=Decimal(str(o)), h=Decimal(str(round(max(o, c) + 0.3, 4))),
                l=Decimal(str(round(min(o, c) - 0.3, 4))), c=Decimal(str(c)),
                v=10.0, source_version="t",
            )
        )
    return bars


def _signals(
    preset: str, bars: list[MarketEvent], cap: int, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[int, str]]:
    monkeypatch.setattr(ira, "ADAPTER_HISTORY_CAP", cap)
    adapter = IndicatorRuleAdapter(symbol="BTC-USDT", preset=preset, name=f"p_{preset}", params={})
    adapter.on_start(CTX)
    out: list[tuple[int, str]] = []
    for i, bar in enumerate(bars):
        for sig in adapter.on_market(bar, CTX):
            out.append((i, sig.direction))
    return out


@pytest.mark.parametrize(
    "preset", ["macd_trend", "rsi_fade", "adx_trend", "ou_fairvalue", "zscore_reversion"]
)
def test_capped_history_emits_identical_signals(
    preset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bars = _bars(1_500)  # cap 400 -> trimmed at bars 800 and 1200
    capped = _signals(preset, bars, 400, monkeypatch)
    unbounded = _signals(preset, bars, 10**9, monkeypatch)
    assert capped == unbounded
    assert len(unbounded) > 2, f"{preset} never fired -- series too tame to prove parity"


def test_opening_range_breakout_parity_needs_a_full_utc_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # this preset reads every bar of the current UTC day (up to 1440 on 1m),
    # the binding constraint behind ADAPTER_HISTORY_CAP's value -- prove the
    # real cap (4096) covers it over a 2.5-day run with trims
    bars = _bars(3_600)
    capped = _signals("opening_range_breakout", bars, 2_048, monkeypatch)
    unbounded = _signals("opening_range_breakout", bars, 10**9, monkeypatch)
    assert capped == unbounded
    assert len(unbounded) > 0


def test_history_really_stays_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ira, "ADAPTER_HISTORY_CAP", 100)
    adapter = IndicatorRuleAdapter(
        symbol="BTC-USDT", preset="macd_trend", name="bound_check", params={}
    )
    adapter.on_start(CTX)
    for bar in _bars(350):
        adapter.on_market(bar, CTX)
    assert len(adapter._closes) <= 200  # 2 * cap
    assert len(adapter._closes) == len(adapter._highs) == len(adapter._timestamps)
