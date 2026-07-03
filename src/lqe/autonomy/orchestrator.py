"""The rule-based orchestrator (docs/02 §2.2, docs/11 §11.6): one
`step()` = one turn of the OBSERVE → HYPOTHESIZE → SEARCH → VALIDATE →
DECIDE → NARRATE loop. Rule-based means no LLM (M9 adds the LLM narrator);
the same state machine runs either way.

Integrity rails this class enforces (docs/02 §2.5):
- It never constructs an `Order` and never touches execution — it only runs
  backtests, reads metrics, and promotes via the gate.
- Nothing reaches the tracked book except through `PromotionGate.check`
  returning PASS, then `TrackedBook.promote` (which re-checks the verdict).
- Degradation → **de-risk first, then re-validate** (docs/02 §2.4). The
  live/tracked config is never edited in place to chase the recent curve;
  a replacement only lands via a fresh gate pass.
- Deterministic: every id is derived from the model + step (not a uuid), the
  Optuna search is seeded, and all backtests are replay-clocked — so the
  audit chain reproduces exactly on replay (a hard rail, docs/11 §11.8).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lqe.analytics.metrics import returns_from_equity, sharpe_ratio
from lqe.analytics.registry import ExperimentRegistry
from lqe.autonomy.books import TrackedBook
from lqe.autonomy.drift import DriftMonitor
from lqe.autonomy.narrator import (
    HypothesisContext,
    Narrator,
    OutcomeContext,
    RuleBasedNarrator,
)
from lqe.autonomy.optimizer import OptunaOptimizer, SearchSpace, safe_search_space
from lqe.autonomy.promotion_gate import GateResult, PromotionGate
from lqe.autonomy.searchable import SearchableModel
from lqe.autonomy.validator import PromotionCandidate, Validator
from lqe.backtest.runner import run_backtest
from lqe.core.clock import ManualClock
from lqe.core.engine import Engine
from lqe.core.events import (
    HypothesisEvent,
    LlmCallEvent,
    NarrationEvent,
    TrialEvent,
    ValidationEvent,
)
from lqe.core.types import Book, Symbol
from lqe.risk.de_risk import DeRiskController

_PERIODS_PER_YEAR = 365.0 * 24.0 * 60.0  # 1-minute bars, 24/7 crypto (matches the Validator)
_INVALID_SCORE = -1.0e9


class OrchestratorState(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_index: int
    focus_model: str
    degraded: bool
    drift_reasons: list[str]
    hypo_id: str
    study_id: str
    candidate_id: str
    best_params: dict[str, Any]
    best_value: float
    verdict: Literal["PASS", "FAIL"]
    promoted: bool
    n_trials_context: int
    narration: str


@dataclass
class Orchestrator:
    validator: Validator
    gate: PromotionGate
    optimizer: OptunaOptimizer
    searchable_models: Sequence[SearchableModel]
    bars: Sequence[Any]
    symbol: Symbol
    starting_cash: Decimal
    run_id: str = "autopilot"
    book: Book = "sandbox"
    seed: int = 0
    n_trials: int = 12
    data_version: str = "sandbox"
    search_fraction: float = 0.7
    tracked_book: TrackedBook = field(default_factory=TrackedBook)
    de_risk: DeRiskController = field(default_factory=DeRiskController)
    drift_monitor: DriftMonitor = field(default_factory=DriftMonitor)
    # The reasoning/explanation layer. Rule-based by default (deterministic,
    # no LLM); an OllamaNarrator only *proposes* safe range refinements and
    # narration — it never optimizes, judges, orders, or clears the kill.
    narrator: Narrator = field(default_factory=RuleBasedNarrator)
    # Optional persistent trial provenance (docs/03 §3.6): when supplied,
    # every trial is recorded and the honest trial count that feeds DSR/PBO
    # is *seeded from prior campaigns*, so re-searching the same data can't
    # smuggle a lucky winner past the deflation. Left None in tests keeps the
    # count purely in-memory (starts at 0) and the audit chain deterministic.
    registry: ExperimentRegistry | None = None

    def __post_init__(self) -> None:
        if not self.searchable_models:
            raise ValueError("orchestrator needs at least one searchable model")
        # A ManualClock the loop sets each step; the audit chain is
        # deterministic because sim_ts is a value we control, not wall time.
        self._clock = ManualClock(datetime.fromtimestamp(0, tz=UTC))
        self.engine = Engine(run_id=self.run_id, book=self.book, clock=self._clock)
        self._step_index = 0
        # Honest catalog-wide count spans campaigns when a registry persists it.
        self._n_trials_context = self.registry.trial_count() if self.registry is not None else 0
        cut = max(2, int(len(self.bars) * self.search_fraction))
        self._search_bars = list(self.bars[:cut])

    # -- one loop turn ----------------------------------------------------

    def step(self, now: datetime) -> OrchestratorState:
        self._clock.set(now)
        self._step_index += 1
        step = self._step_index
        focus = self.searchable_models[(step - 1) % len(self.searchable_models)]

        degraded, drift_reasons = self._observe(focus, now)
        hypo_id, space = self._hypothesize(focus, step, degraded, drift_reasons)
        study_id, best_params, best_value = self._search(focus, step, hypo_id, space)
        candidate = self._candidate(focus, step, hypo_id, study_id, best_params)
        gate_result = self._validate(focus, candidate)
        promoted = self._decide(focus, candidate, best_params, gate_result, now)
        narration = self._narrate(focus, degraded, gate_result, promoted)

        return OrchestratorState(
            step_index=step,
            focus_model=focus.model_id,
            degraded=degraded,
            drift_reasons=drift_reasons,
            hypo_id=hypo_id,
            study_id=study_id,
            candidate_id=candidate.candidate_id,
            best_params=best_params,
            best_value=best_value,
            verdict=gate_result.verdict,
            promoted=promoted,
            n_trials_context=self._n_trials_context,
            narration=narration,
        )

    def run(self, *, steps: int, start: datetime) -> list[OrchestratorState]:
        return [self.step(start) for _ in range(steps)]

    # -- phases -----------------------------------------------------------

    def _observe(self, focus: SearchableModel, now: datetime) -> tuple[bool, list[str]]:
        entry = self.tracked_book.get(focus.model_id)
        if entry is None:
            return False, []
        recent = self._returns_for(focus, entry.params, self.bars)
        verdict = self.drift_monitor.evaluate(recent)
        if not verdict.drifting:
            return False, []
        reasons = [r.value for r in verdict.reasons]
        # Protect first (docs/02 §2.4): de-risk the degraded tracked model,
        # then this same step re-searches for a gate-passed replacement.
        event = self.de_risk.apply(
            model_id=focus.model_id, action="REDUCE", reason="; ".join(reasons)
        )
        self.engine.emit("DeRiskEvent", event)
        return True, reasons

    def _hypothesize(
        self, focus: SearchableModel, step: int, degraded: bool, reasons: list[str]
    ) -> tuple[str, SearchSpace]:
        hypo_id = f"hypo:{focus.model_id}:{step}"
        # The narrator may propose narrower ranges; safe_search_space clamps
        # them inside the model's vetted defaults, so the space actually
        # searched can only ever be a safe refinement of the manifest.
        ctx = HypothesisContext(
            model_id=focus.model_id,
            family=focus.family,
            default_ranges={n: (r.low, r.high) for n, r in focus.space.ranges.items()},
            degraded=degraded,
            drift_reasons=tuple(reasons),
            step=step,
        )
        proposed = self.narrator.propose_ranges(ctx)
        self._audit_llm_calls()
        space = safe_search_space(focus.space, proposed)

        rationale = (
            f"degradation on tracked {focus.model_id} ({', '.join(reasons)}); "
            "re-searching for a gate-passed replacement"
            if degraded
            else f"scheduled sandbox exploration of {focus.model_id} ({focus.family})"
        )
        self.engine.emit(
            "HypothesisEvent",
            HypothesisEvent(
                hypo_id=hypo_id,
                rationale=rationale,
                target_models=[focus.model_id],
                proposed_space=_space_to_dict(space),
                regime="unclassified",
            ),
        )
        return hypo_id, space

    def _search(
        self, focus: SearchableModel, step: int, hypo_id: str, space: SearchSpace
    ) -> tuple[str, dict[str, Any], float]:
        study_id = f"study:{focus.model_id}:{step}"
        result = self.optimizer.study(
            space, self._objective(focus), n_trials=self.n_trials, seed=self.seed + step
        )
        for trial in result.trials:
            self._n_trials_context += 1
            trial_id = f"trial:{focus.model_id}:{step}:{trial.index}"
            self.engine.emit(
                "TrialEvent",
                TrialEvent(
                    trial_id=trial_id,
                    hypo_id=hypo_id,
                    study_id=study_id,
                    params=trial.params,
                    oos_metric=trial.value,
                    seed=result.seed,
                    index=trial.index,
                ),
            )
            if self.registry is not None:
                # Run-scoped PK so distinct campaigns accumulate but an
                # identical re-run REPLACEs (no double-count of the same effort).
                self.registry.record_trial(
                    trial_id=f"{self.run_id}:{trial_id}",
                    run_id=self.run_id,
                    study_id=study_id,
                    hypo_id=hypo_id,
                    params=trial.params,
                    oos_metric=trial.value,
                    seed=result.seed,
                    idx=trial.index,
                    created_at=self._clock.now(),
                )
        return study_id, result.best_params, result.best_value

    def _candidate(
        self,
        focus: SearchableModel,
        step: int,
        hypo_id: str,
        study_id: str,
        best_params: dict[str, Any],
    ) -> PromotionCandidate:
        return PromotionCandidate(
            candidate_id=f"cand:{focus.model_id}:{step}",
            model_id=focus.model_id,
            params=best_params,
            book="sandbox",
            hypo_id=hypo_id,
            study_id=study_id,
            data_version=self.data_version,
            seed=self.seed + step,
            n_trials_context=self._n_trials_context,  # honest catalog-wide count
        )

    def _validate(self, focus: SearchableModel, candidate: PromotionCandidate) -> GateResult:
        result = self.validator.validate(
            candidate,
            bars=self.bars,
            symbol=self.symbol,
            strategy_factory=lambda: focus.build(self.symbol, candidate.params),
            starting_cash=self.starting_cash,
        )
        gate_result = self.gate.check(candidate, result, n_periods=len(self.bars))
        self.engine.emit(
            "ValidationEvent",
            ValidationEvent(
                candidate_id=candidate.candidate_id,
                result=gate_result.verdict,
                dsr=result.dsr,
                pbo=result.pbo,
                cost_survived=result.cost_survived,
                beats_equal_weight=result.beats_equal_weight,
                evidence=gate_result.evidence,
            ),
        )
        return gate_result

    def _decide(
        self,
        focus: SearchableModel,
        candidate: PromotionCandidate,
        best_params: dict[str, Any],
        gate_result: GateResult,
        now: datetime,
    ) -> bool:
        if gate_result.verdict != "PASS":
            return False  # FAIL: ValidationEvent already logged; nothing promoted
        event = self.tracked_book.promote(
            model_id=focus.model_id,
            params=best_params,
            candidate_id=candidate.candidate_id,
            gate_result=gate_result,
            now=now,
        )
        self.engine.emit("PromotionEvent", event)
        return True

    def _narrate(
        self, focus: SearchableModel, degraded: bool, gate_result: GateResult, promoted: bool
    ) -> str:
        fail_reasons = tuple(str(r) for r in gate_result.evidence.get("fail_reasons", []))
        ctx = OutcomeContext(
            model_id=focus.model_id,
            degraded=degraded,
            verdict=gate_result.verdict,
            promoted=promoted,
            dsr=gate_result.dsr,
            pbo=gate_result.pbo,
            fail_reasons=fail_reasons,
        )
        narration = self.narrator.narrate(ctx)
        self._audit_llm_calls()
        self.engine.emit("NarrationEvent", NarrationEvent(text=narration, refs=[]))
        return narration

    # -- helpers ----------------------------------------------------------

    def _audit_llm_calls(self) -> None:
        """Drain any LLM exchanges the narrator just made and log each as an
        `LlmCallEvent` (docs/11 §11.8), so the session replays from the
        recorded decision rather than re-invoking the stochastic model. The
        rule-based narrator drains nothing — the audit is unchanged from M8."""
        for call in self.narrator.drain_calls():
            self.engine.emit(
                "LlmCallEvent",
                LlmCallEvent(
                    purpose=call.purpose,
                    model=call.model,
                    temperature=call.temperature,
                    seed=call.seed,
                    prompt=call.prompt,
                    response=call.response,
                    accepted_tools=call.accepted_tools,
                    rejected=call.rejected,
                ),
            )

    def _objective(self, focus: SearchableModel) -> Any:
        def objective(params: dict[str, Any]) -> float:
            try:
                strategy = focus.build(self.symbol, params)
            except (ValueError, KeyError):
                return _INVALID_SCORE  # invalid param combo (e.g. fast >= slow)
            session = run_backtest(
                run_id=f"search:{focus.model_id}", symbol=self.symbol,
                bars=self._search_bars, strategy=strategy, starting_cash=self.starting_cash,
            )
            score = sharpe_ratio(
                returns_from_equity(session.equity_curve), periods_per_year=_PERIODS_PER_YEAR
            )
            return score if math.isfinite(score) else _INVALID_SCORE

        return objective

    def _returns_for(
        self, focus: SearchableModel, params: dict[str, Any], bars: Sequence[Any]
    ) -> list[float]:
        strategy = focus.build(self.symbol, params)
        session = run_backtest(
            run_id=f"observe:{focus.model_id}", symbol=self.symbol,
            bars=bars, strategy=strategy, starting_cash=self.starting_cash,
        )
        return [float(x) for x in returns_from_equity(session.equity_curve)]


def _space_to_dict(space: SearchSpace) -> dict[str, Any]:
    return {
        name: {"low": rng.low, "high": rng.high, "is_int": rng.is_int}
        for name, rng in space.ranges.items()
    }
