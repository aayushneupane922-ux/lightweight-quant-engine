"""DSR correct on known inputs (docs/10 M4): a genuine edge survives
deflation under many trials; noise collapses toward zero — and more
trials must never *increase* DSR for the same return series.
"""

from __future__ import annotations

import numpy as np

from lqe.analytics.dsr import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    norm_cdf,
    norm_ppf,
)


def test_norm_cdf_ppf_are_inverses() -> None:
    for p in (0.001, 0.05, 0.25, 0.5, 0.75, 0.95, 0.999):
        assert abs(norm_cdf(norm_ppf(p)) - p) < 1e-6


def test_norm_cdf_standard_values() -> None:
    assert abs(norm_cdf(0.0) - 0.5) < 1e-9
    assert norm_cdf(-10) < 1e-6
    assert norm_cdf(10) > 1 - 1e-6


def test_expected_max_sharpe_grows_with_trials() -> None:
    e1 = expected_max_sharpe(1.0, 1)
    e10 = expected_max_sharpe(1.0, 10)
    e1000 = expected_max_sharpe(1.0, 1000)
    assert e1 == 0.0  # a single trial has no deflation baseline
    assert e10 < e1000  # searching harder raises the bar for "lucky"


def test_dsr_strong_genuine_edge_survives_many_trials() -> None:
    rng = np.random.default_rng(42)
    strong_returns = rng.normal(loc=0.002, scale=0.01, size=500)
    dsr_few = deflated_sharpe_ratio(strong_returns, n_trials=1)
    dsr_many = deflated_sharpe_ratio(strong_returns, n_trials=1000)
    assert dsr_few > 0.99
    assert dsr_many > 0.8  # a real edge should mostly survive heavy deflation


def test_dsr_pure_noise_collapses_under_many_trials() -> None:
    rng = np.random.default_rng(42)
    noise_returns = rng.normal(loc=0.0, scale=0.01, size=500)
    dsr_many = deflated_sharpe_ratio(noise_returns, n_trials=1000)
    assert dsr_many < 0.01


def test_dsr_never_increases_with_more_trials_for_the_same_returns() -> None:
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.0005, scale=0.01, size=300)
    trial_counts = (1, 5, 20, 100, 1000, 10000)
    dsrs = [deflated_sharpe_ratio(returns, n_trials=n) for n in trial_counts]
    assert all(a >= b for a, b in zip(dsrs, dsrs[1:], strict=False))


def test_dsr_degenerate_inputs_return_zero() -> None:
    assert deflated_sharpe_ratio(np.array([]), n_trials=1) == 0.0
    assert deflated_sharpe_ratio(np.array([0.01]), n_trials=1) == 0.0
    assert deflated_sharpe_ratio(np.zeros(100), n_trials=1) == 0.0
