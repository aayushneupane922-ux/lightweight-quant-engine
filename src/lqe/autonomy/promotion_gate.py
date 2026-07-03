"""The `PromotionGate` (docs/04 §4.1, docs/11 §11.6): the only code that may
construct a `GateResult`, and therefore the only code that may decide PASS.
`tests/safety/test_promotion_gate_sole_verdict.py` enforces this with an
AST/grep scan, the same discipline as `make_order`.

Fail-closed by construction: `_passes` is a conjunction of every §4.1
requirement, so a missing/`None`/degenerate input can only push the
verdict toward FAIL, never toward PASS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lqe.autonomy.validator import PromotionCandidate, ValidationResult


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Literal["PASS", "FAIL"]
    dsr: float
    pbo: float
    cost_survived: bool
    beats_equal_weight: bool
    beats_random: bool
    walk_forward_oos: float
    evidence: dict[str, Any]


@dataclass(frozen=True)
class GateThresholds:
    min_dsr: float = 0.95
    max_pbo: float = 0.5
    min_trades: int = 30
    min_periods: int = 10_000


class PromotionGate:
    def __init__(self, *, thresholds: GateThresholds | None = None) -> None:
        self._thresholds = thresholds or GateThresholds()

    def check(
        self, candidate: PromotionCandidate, result: ValidationResult, *, n_periods: int
    ) -> GateResult:
        reasons = self._fail_reasons(result, n_periods=n_periods)
        verdict: Literal["PASS", "FAIL"] = "FAIL" if reasons else "PASS"
        evidence = {
            **result.evidence,
            "candidate_id": candidate.candidate_id,
            "model_id": candidate.model_id,
            "n_trials_context": candidate.n_trials_context,
            "n_periods": n_periods,
            "fail_reasons": reasons,
        }
        return GateResult(
            verdict=verdict,
            dsr=result.dsr,
            pbo=result.pbo,
            cost_survived=result.cost_survived,
            beats_equal_weight=result.beats_equal_weight,
            beats_random=result.beats_random,
            walk_forward_oos=result.walk_forward_oos_sharpe,
            evidence=evidence,
        )

    def _fail_reasons(self, result: ValidationResult, *, n_periods: int) -> list[str]:
        thresholds = self._thresholds
        reasons: list[str] = []
        if result.walk_forward_oos_sharpe <= 0:
            reasons.append("walk_forward_oos_sharpe <= 0")
        if result.dsr < thresholds.min_dsr:
            reasons.append(f"dsr {result.dsr:.4f} < min_dsr {thresholds.min_dsr}")
        if result.pbo > thresholds.max_pbo:
            reasons.append(f"pbo {result.pbo:.4f} > max_pbo {thresholds.max_pbo}")
        if not result.cost_survived:
            reasons.append("does not survive the cost-sensitivity sweep")
        if not result.beats_equal_weight:
            reasons.append("does not beat equal-weight/buy-hold")
        if not result.beats_random:
            reasons.append("does not beat the random-entry control")
        if result.n_trades < thresholds.min_trades:
            reasons.append(f"n_trades {result.n_trades} < min_trades {thresholds.min_trades}")
        if n_periods < thresholds.min_periods:
            reasons.append(f"n_periods {n_periods} < min_periods {thresholds.min_periods}")
        return reasons
