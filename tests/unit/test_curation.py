"""docs/14 §3 (v4): correlation curation rejects the 40th trend clone, but
never rejects a genuinely better version of an existing driver just for
being correlated to it.
"""

from __future__ import annotations

import numpy as np
import pytest

from lqe.models.curation import correlation_curation_check

rng = np.random.default_rng(seed=11)


def _series(n: int = 200) -> list[float]:
    return rng.normal(size=n).tolist()


def test_empty_catalog_always_passes() -> None:
    result = correlation_curation_check(
        candidate_id="first_model", candidate_returns=_series(),
        candidate_metric=0.5, existing_returns={}, existing_metrics={},
    )
    assert result.passed
    assert result.reasons == []


def test_redundant_and_not_better_is_quarantined() -> None:
    base = _series()
    result = correlation_curation_check(
        candidate_id="trend_clone_40", candidate_returns=list(base),
        candidate_metric=0.3,
        existing_returns={"trend_ma_cross": base},
        existing_metrics={"trend_ma_cross": 0.9},
    )
    assert not result.passed
    assert result.most_correlated_to == "trend_ma_cross"
    assert result.correlation == pytest.approx(1.0, abs=1e-9)
    assert "duplicate driver" in result.reasons[0]


def test_redundant_but_clearly_better_still_passes() -> None:
    # identical return stream (perfectly redundant) but a strictly better
    # metric -- docs/14 §3's "and not clearly better" carve-out.
    base = _series()
    result = correlation_curation_check(
        candidate_id="trend_v2", candidate_returns=list(base),
        candidate_metric=1.2,
        existing_returns={"trend_ma_cross": base},
        existing_metrics={"trend_ma_cross": 0.9},
    )
    assert result.passed
    assert result.most_correlated_to == "trend_ma_cross"


def test_uncorrelated_candidate_passes_regardless_of_metric() -> None:
    existing = _series()
    # a genuinely different, independent return stream
    candidate = rng.normal(size=len(existing)).tolist()
    result = correlation_curation_check(
        candidate_id="carry_basis_1", candidate_returns=candidate,
        candidate_metric=0.1,  # even a weak metric is fine -- it's not redundant
        existing_returns={"trend_ma_cross": existing},
        existing_metrics={"trend_ma_cross": 0.9},
    )
    assert result.passed
    assert abs(result.correlation or 0.0) < 0.5


def test_checks_against_the_most_correlated_existing_model() -> None:
    base = _series()
    unrelated = rng.normal(size=len(base)).tolist()
    result = correlation_curation_check(
        candidate_id="clone", candidate_returns=list(base), candidate_metric=0.1,
        existing_returns={"unrelated_model": unrelated, "near_identical": base},
        existing_metrics={"unrelated_model": 5.0, "near_identical": 0.9},
    )
    # must compare against near_identical (the actually-correlated one), not
    # unrelated_model, even though unrelated_model has a much better metric
    assert result.most_correlated_to == "near_identical"
    assert not result.passed


def test_mismatched_existing_returns_and_metrics_keys_raises() -> None:
    with pytest.raises(ValueError, match="same model ids"):
        correlation_curation_check(
            candidate_id="x", candidate_returns=_series(), candidate_metric=0.1,
            existing_returns={"a": _series()}, existing_metrics={"b": 0.5},
        )


def test_misaligned_return_stream_lengths_raises() -> None:
    with pytest.raises(ValueError, match="aligned to the same length"):
        correlation_curation_check(
            candidate_id="x", candidate_returns=_series(50), candidate_metric=0.1,
            existing_returns={"a": _series(100)}, existing_metrics={"a": 0.5},
        )
