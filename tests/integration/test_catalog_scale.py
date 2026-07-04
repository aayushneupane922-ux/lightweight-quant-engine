"""The scaled catalog (docs/10 M11, docs/03 §3.1/§3.6): 50+ models reached
by config, honestly gated — native models admit and run deterministically,
heavy-lib models quarantine transparently when the optional extra is
absent, and nothing is ever ranked `validated` without a gate PASS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.util import find_spec

import pytest

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import build_scaled_catalog

SYMBOL: Symbol = "BTC-USDT"

# Every backing lib the scaled catalog's heavy adapters depend on (docs/10 M13:
# once the full 'models' extra is installed, e.g. this machine post-M13,
# nothing quarantines — the assertion below only makes sense when at least
# one is genuinely absent (e.g. CI, which installs '.[ui,search,dev]' only).
_HEAVY_LIBS = (
    "statsmodels", "arch", "hmmlearn", "ruptures", "skfolio", "pypfopt",
    "riskfolio", "sklearn", "lightgbm",
)
_all_present = all(find_spec(name) is not None for name in _HEAVY_LIBS)


def _bars(n: int = 200) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 12) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def test_at_least_fifty_models_are_available() -> None:
    _, results = build_scaled_catalog(SYMBOL)
    assert len(results) >= 50
    assert len({r.model_id for r in results}) == len(results)  # no duplicate ids


def test_native_models_admit_and_span_four_families() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    admitted = catalog.all()
    assert len(admitted) >= 40
    families = {e.manifest.family for e in admitted}
    assert families >= {"trend", "momentum", "mean_reversion", "volatility"}


def test_every_admitted_model_is_unproven_until_gated() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    # honesty: breadth does not confer validation — the gate does
    assert all(e.manifest.status == "unproven" for e in catalog.all())


@pytest.mark.skipif(
    _all_present,
    reason="full 'models' extra installed; nothing quarantines here — see "
    "test_all_models_admit_once_the_full_models_extra_is_installed",
)
def test_heavy_lib_models_quarantine_transparently_when_absent() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    quarantined = catalog.quarantined()
    assert quarantined, "heavy-lib models should quarantine without the 'models' extra"
    # transparent: each carries a real reason, never silently dropped
    for record in quarantined:
        assert record.reasons
        assert "models" in record.reasons[0]  # the pip install '.[models]' hint


@pytest.mark.skipif(
    not _all_present,
    reason="requires the full 'models' extra (docs/10 M13) to be installed",
)
def test_all_models_admit_once_the_full_models_extra_is_installed() -> None:
    # 85 as of docs/14 (v4) M23's in-progress sleeve additions (was 51 at
    # v3.0) -- bump this again when M24's carry/basis sleeve lands.
    catalog, _ = build_scaled_catalog(SYMBOL)
    assert not catalog.quarantined()
    assert len(catalog.all()) == 85


def test_the_deliberately_weak_control_is_present() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    assert any(e.manifest.id == "naive_always_long" for e in catalog.all())


def test_every_admitted_model_carries_a_sleeve_tag() -> None:
    # docs/14 §3 (v4): every model must be tagged with its return-driver
    # sleeve so the diversification score is computable; "control" is the
    # one deliberate exception (naive_always_long isn't a diversification bet).
    catalog, _ = build_scaled_catalog(SYMBOL)
    for entry in catalog.all():
        assert entry.manifest.sleeve, f"{entry.manifest.id} has no sleeve tag"


def test_sleeves_span_multiple_return_drivers_not_just_trend() -> None:
    # docs/14 §1: diversification lives across sleeves -- the pre-v4 catalog
    # is trend/momentum/mean-reversion/volatility-heavy by construction (its
    # own §6/§11 build order), so this only pins that *today's* sleeve mix
    # isn't a single monoculture; v4's M23 sleeves add the real diversifiers.
    catalog, _ = build_scaled_catalog(SYMBOL)
    sleeves = {e.manifest.sleeve for e in catalog.all()}
    assert sleeves >= {"trend_momentum", "mean_reversion", "volatility"}


def test_cross_sectional_sleeve_is_now_represented() -> None:
    # docs/14 sleeve C (v4): the engine's multi-symbol Context extension
    # unlocked real cross-sectional strategies -- confirm they're actually
    # registered, not just designed on paper.
    catalog, _ = build_scaled_catalog(SYMBOL)
    xsec = [e for e in catalog.all() if e.manifest.sleeve == "cross_sectional"]
    assert len(xsec) >= 4
    assert all(e.manifest.id.startswith("xsec_") for e in xsec)


def test_admitted_models_run_a_deterministic_backtest() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    bars = _bars()
    # sample a few admitted models across families; each must run and be
    # bit-reproducible (same audit head hash on a second run)
    sample = catalog.all()[:6]
    for entry in sample:
        a = run_backtest(
            run_id=f"scale:{entry.manifest.id}:a", symbol=SYMBOL, bars=bars,
            strategy=entry.strategy_factory(), starting_cash=Decimal("10000"),
        )
        b = run_backtest(
            run_id=f"scale:{entry.manifest.id}:a", symbol=SYMBOL, bars=bars,
            strategy=entry.strategy_factory(), starting_cash=Decimal("10000"),
        )
        assert a.engine.audit.verify()
        assert a.engine.audit.head_hash == b.engine.audit.head_hash
