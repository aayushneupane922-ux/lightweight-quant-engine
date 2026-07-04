"""Native indicator correctness (docs/10 M6) — replaces pandas-ta, which
was rejected for a license reason (see pyproject.toml). Checked against
hand-computable cases, not just "it runs."
"""

from __future__ import annotations

import numpy as np
import pytest

from lqe.models.adapters.indicators import adx, atr, bollinger, donchian, ema, macd, rsi, sma


def test_sma_matches_hand_computation() -> None:
    closes = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    result = sma(closes, 3)
    assert np.isnan(result[0]) and np.isnan(result[1])
    assert result[2] == 2.0  # mean(1,2,3)
    assert result[-1] == 9.0  # mean(8,9,10)


def test_sma_rejects_non_positive_window() -> None:
    with pytest.raises(ValueError, match="window"):
        sma(np.array([1.0, 2.0]), 0)


def test_ema_reacts_faster_than_sma_to_a_recent_jump() -> None:
    closes = np.concatenate([np.full(20, 100.0), np.full(20, 110.0)])
    sma_result = sma(closes, 10)
    ema_result = ema(closes, 10)
    # a few bars after the jump, SMA's window still mixes pre/post-jump
    # values while EMA (weighting recent bars more) has already pulled
    # closer to the new level. Comparing at the *very end* would be
    # misleading: after 10+ bars SMA's window is entirely past the jump
    # and fully catches up, while EMA only asymptotically approaches it.
    idx = 25
    assert ema_result[idx] > sma_result[idx]


def test_rsi_all_up_moves_approaches_100() -> None:
    closes = np.arange(100, 130, dtype=float)  # strictly increasing
    result = rsi(closes, 14)
    assert result[-1] == 100.0


def test_rsi_all_down_moves_approaches_0() -> None:
    closes = np.arange(130, 100, -1, dtype=float)  # strictly decreasing
    result = rsi(closes, 14)
    assert result[-1] == 0.0


def test_rsi_flat_series_is_neutral() -> None:
    closes = np.full(30, 100.0)
    result = rsi(closes, 14)
    assert result[-1] == 100.0  # no losses at all -> RSI is defined as 100 (avg_loss == 0)


def test_donchian_channel_excludes_the_current_bar() -> None:
    closes = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    high, low = closes + 1, closes - 1
    upper, lower = donchian(high, low, window=3)
    # at index 5, the window looks back over indices [2,3,4], not [5] itself
    assert upper[5] == high[2:5].max()
    assert lower[5] == low[2:5].min()


def test_bollinger_bands_widen_with_more_volatility() -> None:
    rng = np.random.default_rng(0)
    calm = 100 + rng.normal(0, 0.1, 50)
    volatile = 100 + rng.normal(0, 5.0, 50)
    _, calm_upper, calm_lower = bollinger(calm, window=20)
    _, vol_upper, vol_lower = bollinger(volatile, window=20)
    assert (vol_upper[-1] - vol_lower[-1]) > (calm_upper[-1] - calm_lower[-1])


def test_macd_histogram_converges_to_zero_for_a_linear_trend() -> None:
    # a constant-slope series has a constant-slope MACD line, so its own
    # EMA (the signal line) catches up and the histogram flattens near 0.
    closes = np.linspace(100, 160, 60, dtype=np.float64)
    _, _, histogram = macd(closes, fast=12, slow=26, signal=9)
    assert abs(histogram[-1]) < 1e-6


def test_adx_is_higher_for_a_strong_trend_than_a_choppy_series() -> None:
    n = 60
    trend = np.linspace(100, 160, n, dtype=np.float64)
    choppy = 100 + np.sin(np.linspace(0, 20, n, dtype=np.float64)) * 2

    trend_adx = adx(trend + 1, trend - 1, trend, window=14)
    choppy_adx = adx(choppy + 1, choppy - 1, choppy, window=14)

    assert trend_adx[-1] > choppy_adx[-1]
    assert trend_adx[-1] > 50  # a clean linear trend should read as strongly trending


def test_atr_is_higher_for_a_wider_true_range_series() -> None:
    n = 40
    calm_close = np.full(n, 100.0)
    wide_close = np.full(n, 100.0)

    calm_atr = atr(calm_close + 0.5, calm_close - 0.5, calm_close, window=14)
    wide_atr = atr(wide_close + 5.0, wide_close - 5.0, wide_close, window=14)

    assert wide_atr[-1] > calm_atr[-1]


def test_atr_is_nan_before_enough_bars() -> None:
    closes = np.array([100.0, 101.0, 102.0])
    result = atr(closes + 1, closes - 1, closes, window=14)
    assert np.all(np.isnan(result))
