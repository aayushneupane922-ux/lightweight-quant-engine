"""PBO correct on known inputs (docs/10 M4): all-noise configs land near a
coin-flip (~0.5); a config with a genuine, stable edge in every block is
essentially never overfit (~0.0).
"""

from __future__ import annotations

import numpy as np
import pytest

from lqe.analytics.pbo import probability_of_backtest_overfitting


def test_pbo_all_noise_configs_is_near_a_coin_flip() -> None:
    rng = np.random.default_rng(7)
    noise_matrix = rng.normal(loc=0.0, scale=0.01, size=(800, 10))
    pbo = probability_of_backtest_overfitting(noise_matrix, n_splits=8)
    assert 0.3 <= pbo <= 0.7


def test_pbo_one_genuinely_better_config_is_low() -> None:
    rng = np.random.default_rng(7)
    matrix = rng.normal(loc=0.0, scale=0.01, size=(800, 10))
    matrix[:, 0] = rng.normal(loc=0.003, scale=0.01, size=800)
    pbo = probability_of_backtest_overfitting(matrix, n_splits=8)
    assert pbo < 0.2


def test_pbo_rejects_a_single_config() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        probability_of_backtest_overfitting(np.zeros((100, 1)), n_splits=4)


def test_pbo_rejects_odd_n_splits() -> None:
    with pytest.raises(ValueError, match="even"):
        probability_of_backtest_overfitting(np.zeros((100, 2)), n_splits=5)


def test_pbo_rejects_too_few_periods_for_the_splits() -> None:
    with pytest.raises(ValueError, match="not enough periods"):
        probability_of_backtest_overfitting(np.zeros((2, 2)), n_splits=8)
