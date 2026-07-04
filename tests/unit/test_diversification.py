"""docs/14 §1 (v4): the diversification score must actually distinguish a
monoculture (N trend clones) from a genuinely diversified set, not just
report "N models" back.
"""

from __future__ import annotations

import numpy as np
import pytest

from lqe.analytics.diversification import (
    average_pairwise_correlation,
    diversification_score,
    effective_number_of_bets,
    max_sleeve_share,
    pairwise_correlation_matrix,
    sleeve_distribution,
)

rng = np.random.default_rng(seed=7)


def _identical_streams(n: int, length: int = 200) -> dict[str, list[float]]:
    base = rng.normal(size=length).tolist()
    return {f"clone_{i}": list(base) for i in range(n)}


def _independent_streams(n: int, length: int = 500) -> dict[str, list[float]]:
    return {f"indep_{i}": rng.normal(size=length).tolist() for i in range(n)}


def test_pairwise_correlation_matrix_requires_at_least_two_models() -> None:
    with pytest.raises(ValueError, match="at least 2 models"):
        pairwise_correlation_matrix({"only_one": [1.0, 2.0, 3.0]})


def test_pairwise_correlation_matrix_requires_aligned_lengths() -> None:
    with pytest.raises(ValueError, match="aligned to the same length"):
        pairwise_correlation_matrix({"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0]})


def test_identical_return_streams_have_average_correlation_near_one() -> None:
    ids, corr = pairwise_correlation_matrix(_identical_streams(4))
    assert len(ids) == 4
    assert average_pairwise_correlation(corr) == pytest.approx(1.0, abs=1e-9)


def test_independent_return_streams_have_low_average_correlation() -> None:
    _, corr = pairwise_correlation_matrix(_independent_streams(6))
    assert abs(average_pairwise_correlation(corr)) < 0.25


def test_effective_number_of_bets_is_one_for_identical_streams() -> None:
    _, corr = pairwise_correlation_matrix(_identical_streams(5))
    assert effective_number_of_bets(corr) == pytest.approx(1.0, abs=1e-6)


def test_effective_number_of_bets_approaches_n_for_independent_streams() -> None:
    n = 8
    _, corr = pairwise_correlation_matrix(_independent_streams(n))
    enb = effective_number_of_bets(corr)
    # not exactly N (finite-sample correlation noise), but close and well
    # above the "all one bet" floor of 1.0 -- the real headline this
    # function exists to report, per docs/14 §1.
    assert n * 0.6 < enb <= n + 1e-6


def test_effective_number_of_bets_is_between_one_and_n_for_a_mixed_set() -> None:
    # 3 near-identical clones + 3 independent streams -> more diversified
    # than a monoculture but less than fully independent.
    clones = _identical_streams(3, length=500)
    indep = _independent_streams(3)
    combined = {**clones, **indep}
    _, corr = pairwise_correlation_matrix(combined)
    enb = effective_number_of_bets(corr)
    assert 1.0 < enb < 6.0


def test_sleeve_distribution_counts_per_sleeve() -> None:
    counts = sleeve_distribution(
        {"a": "trend_momentum", "b": "trend_momentum", "c": "mean_reversion"}
    )
    assert counts == {"trend_momentum": 2, "mean_reversion": 1}


def test_max_sleeve_share_flags_a_dominant_sleeve() -> None:
    sleeve_by_model = {f"trend_{i}": "trend_momentum" for i in range(9)}
    sleeve_by_model["carry_0"] = "carry_basis"
    dominant, share = max_sleeve_share(sleeve_by_model)
    assert dominant == "trend_momentum"
    assert share == pytest.approx(0.9)


def test_max_sleeve_share_requires_at_least_one_model() -> None:
    with pytest.raises(ValueError, match="no models"):
        max_sleeve_share({})


def test_diversification_score_end_to_end_for_a_monoculture() -> None:
    returns = _identical_streams(5)
    sleeves = {mid: "trend_momentum" for mid in returns}
    score = diversification_score(returns, sleeves)
    assert score.n_models == 5
    assert score.average_pairwise_correlation == pytest.approx(1.0, abs=1e-9)
    assert score.effective_number_of_bets == pytest.approx(1.0, abs=1e-6)
    assert score.n_sleeves == 1
    assert score.dominant_sleeve == "trend_momentum"
    assert score.max_sleeve_share == pytest.approx(1.0)


def test_diversification_score_end_to_end_for_a_diversified_set() -> None:
    returns = _independent_streams(8)
    sleeve_names = [
        "trend_momentum", "mean_reversion", "cross_sectional", "stat_arb",
        "volatility", "carry_basis", "seasonality", "allocator",
    ]
    sleeves = dict(zip(returns.keys(), sleeve_names, strict=True))
    score = diversification_score(returns, sleeves)
    assert score.n_sleeves == 8
    assert score.max_sleeve_share == pytest.approx(1 / 8)
    assert score.effective_number_of_bets > 4.0


def test_diversification_score_rejects_mismatched_model_ids() -> None:
    with pytest.raises(ValueError, match="same model ids"):
        diversification_score(
            {"a": [1.0, 2.0], "b": [2.0, 1.0]}, {"a": "trend_momentum"}
        )
