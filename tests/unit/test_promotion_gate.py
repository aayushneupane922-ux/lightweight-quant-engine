"""docs/10 M4: the gate FAILs an overfit candidate and PASSes a robust
synthetic one. Uses crafted `ValidationResult` evidence directly so the
gate's decision logic is tested in isolation from the (much slower) full
walk-forward machinery.
"""

from __future__ import annotations

from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.validator import PromotionCandidate, ValidationResult

CANDIDATE = PromotionCandidate(
    candidate_id="cand-1",
    model_id="trend_ma_cross",
    params={"fast": 12, "slow": 48},
    book="sandbox",
    hypo_id="H-1",
    study_id="S-1",
    data_version="dv-1",
    seed=1,
    n_trials_context=500,
)

OVERFIT_RESULT = ValidationResult(
    walk_forward_oos_sharpe=-0.3,
    dsr=0.10,
    pbo=0.85,
    cost_survived=False,
    beats_equal_weight=False,
    beats_random=False,
    n_trades=12,
    evidence={"note": "overfit synthetic"},
)

ROBUST_RESULT = ValidationResult(
    walk_forward_oos_sharpe=1.2,
    dsr=0.97,
    pbo=0.10,
    cost_survived=True,
    beats_equal_weight=True,
    beats_random=True,
    n_trades=250,
    evidence={"note": "robust synthetic"},
)


def test_gate_fails_an_overfit_candidate() -> None:
    gate = PromotionGate()
    result = gate.check(CANDIDATE, OVERFIT_RESULT, n_periods=50_000)
    assert result.verdict == "FAIL"
    assert len(result.evidence["fail_reasons"]) > 0


def test_gate_passes_a_robust_synthetic_candidate() -> None:
    gate = PromotionGate()
    result = gate.check(CANDIDATE, ROBUST_RESULT, n_periods=50_000)
    assert result.verdict == "PASS"
    assert result.evidence["fail_reasons"] == []


def test_gate_fails_on_insufficient_sample_even_if_metrics_look_good() -> None:
    gate = PromotionGate()
    result = gate.check(CANDIDATE, ROBUST_RESULT, n_periods=100)  # too few periods
    assert result.verdict == "FAIL"
    assert any("n_periods" in reason for reason in result.evidence["fail_reasons"])


def test_gate_fails_on_insufficient_trade_count() -> None:
    thin_trades = ROBUST_RESULT.model_copy(update={"n_trades": 3})
    gate = PromotionGate()
    result = gate.check(CANDIDATE, thin_trades, n_periods=50_000)
    assert result.verdict == "FAIL"
    assert any("n_trades" in reason for reason in result.evidence["fail_reasons"])


def test_custom_thresholds_are_respected() -> None:
    lenient_thresholds = GateThresholds(min_dsr=0.05, max_pbo=0.9, min_trades=1, min_periods=1)
    lenient_gate = PromotionGate(thresholds=lenient_thresholds)
    result = lenient_gate.check(CANDIDATE, OVERFIT_RESULT, n_periods=50)
    # still fails on cost/benchmark/sharpe, but no longer on dsr/pbo/trades/periods
    reasons = result.evidence["fail_reasons"]
    assert not any(key in r for r in reasons for key in ("dsr", "pbo", "n_trades", "n_periods"))


def test_gate_result_evidence_carries_candidate_provenance() -> None:
    gate = PromotionGate()
    result = gate.check(CANDIDATE, ROBUST_RESULT, n_periods=50_000)
    assert result.evidence["candidate_id"] == "cand-1"
    assert result.evidence["model_id"] == "trend_ma_cross"
    assert result.evidence["n_trials_context"] == 500
