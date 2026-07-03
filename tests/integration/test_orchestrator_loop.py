"""The rule-based autonomy loop end-to-end (docs/02 §2.2, docs/10 M8):
observe→hypothesize→search→validate→decide→narrate, all audited; the gate
is un-bypassable; degradation de-risks then re-validates (never chases);
sandbox and tracked are never conflated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.autonomy.books import TrackedBook
from lqe.autonomy.drift import DriftMonitor, DriftReason, DriftVerdict
from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateResult, GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(n: int = 300) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 13) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=START + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def _orch(
    *,
    lenient_gate: bool,
    drift_monitor: DriftMonitor | None = None,
    tracked_book: TrackedBook | None = None,
) -> Orchestrator:
    thresholds = (
        GateThresholds(min_periods=1, min_trades=1, min_dsr=0.0, max_pbo=1.0)
        if lenient_gate
        else GateThresholds()  # strict defaults -> effectively unreachable on synthetic data
    )
    extra: dict[str, object] = {}
    if drift_monitor is not None:
        extra["drift_monitor"] = drift_monitor
    if tracked_book is not None:
        extra["tracked_book"] = tracked_book
    return Orchestrator(
        validator=Validator(n_folds=2, random_control_reps=3),
        gate=PromotionGate(thresholds=thresholds),
        optimizer=OptunaOptimizer(),
        searchable_models=default_searchable_models(),
        bars=_bars(),
        symbol=SYMBOL,
        starting_cash=Decimal("10000"),
        seed=1,
        n_trials=6,
        **extra,  # type: ignore[arg-type]
    )


def _passing_gate() -> GateResult:
    return GateResult(
        verdict="PASS", dsr=0.99, pbo=0.1, cost_survived=True, beats_equal_weight=True,
        beats_random=True, walk_forward_oos=0.5, evidence={},
    )


class _AlwaysDrift(DriftMonitor):
    """Forces the degradation branch so the de-risk-then-revalidate response
    can be exercised deterministically, independent of synthetic-data luck."""

    def evaluate(self, returns: list[float]) -> DriftVerdict:
        return DriftVerdict(True, (DriftReason.DEGRADED,), 0.0, 1.0, 0.0)


@pytest.mark.filterwarnings("ignore")
def test_loop_runs_all_phases_and_audits_every_step() -> None:
    orch = _orch(lenient_gate=True)
    orch.run(steps=3, start=START)
    types = {e.type for e in orch.engine.audit.records}
    assert {"HypothesisEvent", "TrialEvent", "ValidationEvent", "NarrationEvent"} <= types
    assert orch.engine.audit.verify()


@pytest.mark.filterwarnings("ignore")
def test_gate_is_unbypassable_under_strict_thresholds() -> None:
    orch = _orch(lenient_gate=False)
    states = orch.run(steps=3, start=START)
    assert all(s.verdict == "FAIL" for s in states)
    assert all(not s.promoted for s in states)
    assert len(orch.tracked_book) == 0
    # no PromotionEvent may exist when nothing passed
    assert not any(e.type == "PromotionEvent" for e in orch.engine.audit.records)


@pytest.mark.filterwarnings("ignore")
def test_promotion_only_via_a_passing_gate_and_is_sandbox_to_tracked() -> None:
    orch = _orch(lenient_gate=True)
    states = orch.run(steps=3, start=START)
    promo_events = [e for e in orch.engine.audit.records if e.type == "PromotionEvent"]
    assert promo_events, "expected at least one promotion under the lenient gate"
    for e in promo_events:
        assert e.payload["from_book"] == "sandbox"
        assert e.payload["to_book"] == "tracked"
    # every promoted step had a PASS verdict
    for s in states:
        if s.promoted:
            assert s.verdict == "PASS"


@pytest.mark.filterwarnings("ignore")
def test_trial_count_accumulates_across_the_catalog() -> None:
    orch = _orch(lenient_gate=True)
    states = orch.run(steps=3, start=START)
    # honest catalog-wide count: strictly increasing, == steps * n_trials
    assert [s.n_trials_context for s in states] == [6, 12, 18]


@pytest.mark.filterwarnings("ignore")
def test_degradation_derisks_then_revalidates_without_chasing() -> None:
    # Pre-seed a tracked entry for the step-1 focus model (trend_ma_cross)
    # so OBSERVE has something to find degrading — deterministic, not
    # dependent on whether synthetic data happens to promote it.
    book = TrackedBook()
    book.promote(
        model_id="trend_ma_cross", params={"fast": 5, "slow": 20},
        candidate_id="seed", gate_result=_passing_gate(), now=START,
    )
    tracked_before = book.get("trend_ma_cross")
    assert tracked_before is not None

    # Strict gate so the re-validation FAILs — this is the honest case: a
    # degraded model gets de-risked, a replacement is searched + validated,
    # and because it doesn't pass, the live config is NOT edited to chase.
    orch = _orch(lenient_gate=False, drift_monitor=_AlwaysDrift(), tracked_book=book)
    states = orch.run(steps=1, start=START)
    step1 = states[0]

    assert step1.focus_model == "trend_ma_cross"
    assert step1.degraded is True
    assert DriftReason.DEGRADED.value in step1.drift_reasons

    # protect first: a DeRiskEvent was emitted, then a fresh validation ran
    assert any(e.type == "DeRiskEvent" for e in orch.engine.audit.records)
    assert any(
        e.type == "ValidationEvent" and e.payload["candidate_id"] == step1.candidate_id
        for e in orch.engine.audit.records
    )
    # never chases: the failed re-validation left the tracked config untouched
    assert step1.promoted is False
    tracked_after = orch.tracked_book.get("trend_ma_cross")
    assert tracked_after is not None
    assert tracked_after.config_version == tracked_before.config_version
    assert tracked_after.params == tracked_before.params
