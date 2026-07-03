"""The orchestrator with an LLM narrator (docs/10 M9): the LLM only
proposes safe range refinements and narration; it cannot bypass the gate,
size an order, or clear the kill. Every LLM exchange is logged for replay,
and the rule-based path stays deterministic and LLM-free.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.autonomy.narrator import HypothesisContext, LlmCallRecord, OutcomeContext
from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(n: int = 220) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 11) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=START + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


class _FakeLLM:
    """A stand-in LLM narrator: proposes a valid narrowing plus an absurd
    out-of-bounds range (which must be clamped), and logs each call."""

    name = "fake_llm"

    def __init__(self) -> None:
        self._calls: list[LlmCallRecord] = []

    def propose_ranges(self, ctx: HypothesisContext) -> dict[str, list[float]]:
        self._calls.append(
            LlmCallRecord(
                purpose="propose_space", model="fake", temperature=0.1, seed=0,
                prompt="p", response="r", accepted_tools=["propose_space"], rejected=1,
            )
        )
        return {"fast": [5, 10], "slow": [10, 9999]}  # slow is out of bounds -> clamped

    def narrate(self, ctx: OutcomeContext) -> str:
        self._calls.append(
            LlmCallRecord(
                purpose="narrate", model="fake", temperature=0.1, seed=0,
                prompt="p2", response="r2", accepted_tools=["narrate"], rejected=0,
            )
        )
        return f"LLM: {ctx.model_id} {'promoted' if ctx.promoted else 'not promoted'}"

    def drain_calls(self) -> list[LlmCallRecord]:
        drained = list(self._calls)
        self._calls.clear()
        return drained


def _orch(**kw: object) -> Orchestrator:
    kw.setdefault("gate", PromotionGate(thresholds=GateThresholds(min_periods=1, min_trades=1)))
    return Orchestrator(
        validator=Validator(n_folds=2, random_control_reps=3),
        optimizer=OptunaOptimizer(),
        searchable_models=default_searchable_models(),
        bars=_bars(),
        symbol=SYMBOL,
        starting_cash=Decimal("10000"),
        seed=1,
        n_trials=5,
        **kw,  # type: ignore[arg-type]
    )


@pytest.mark.filterwarnings("ignore")
def test_llm_calls_are_logged_for_replay() -> None:
    orch = _orch(narrator=_FakeLLM())
    orch.run(steps=1, start=START)
    types = Counter(e.type for e in orch.engine.audit.records)
    assert types["LlmCallEvent"] == 2  # one propose_space + one narrate
    assert orch.engine.audit.verify()
    llm_events = [e for e in orch.engine.audit.records if e.type == "LlmCallEvent"]
    # provenance is complete enough to replay from (prompt + response + settings)
    for e in llm_events:
        assert {"prompt", "response", "model", "temperature", "seed"} <= set(e.payload)


@pytest.mark.filterwarnings("ignore")
def test_llm_proposal_is_clamped_into_the_vetted_space() -> None:
    orch = _orch(narrator=_FakeLLM())
    orch.run(steps=1, start=START)
    hyp = next(e for e in orch.engine.audit.records if e.type == "HypothesisEvent")
    space = hyp.payload["proposed_space"]
    # fast narrowed as proposed; slow's absurd 9999 clamped back to the default 80
    assert space["fast"]["low"] == 5.0 and space["fast"]["high"] == 10.0
    assert space["slow"]["high"] == 80.0


@pytest.mark.filterwarnings("ignore")
def test_llm_cannot_bypass_the_gate() -> None:
    # strict gate: even with the LLM proposing and narrating, nothing is
    # promoted without a real PASS — the LLM never touches the verdict.
    orch = _orch(narrator=_FakeLLM(), gate=PromotionGate(thresholds=GateThresholds()))
    states = orch.run(steps=2, start=START)
    assert all(s.verdict == "FAIL" for s in states)
    assert not any(e.type == "PromotionEvent" for e in orch.engine.audit.records)
    assert len(orch.tracked_book) == 0


@pytest.mark.filterwarnings("ignore")
def test_rule_based_path_stays_llm_free_and_deterministic() -> None:
    a = _orch()  # default narrator = rule-based
    a.run(steps=2, start=START)
    b = _orch()
    b.run(steps=2, start=START)
    assert not any(e.type == "LlmCallEvent" for e in a.engine.audit.records)
    assert a.engine.audit.head_hash == b.engine.audit.head_hash  # deterministic
