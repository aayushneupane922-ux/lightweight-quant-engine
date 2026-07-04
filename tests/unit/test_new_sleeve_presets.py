"""docs/14 (v4) M23: the 10 new `IndicatorRuleAdapter` presets added for
sleeves B (mean-reversion), E (volatility), G (breakout/structure), H
(seasonality/calendar), and I (regime overlay) -- each tested for the
specific behavior its docstring claims, not just "constructs."
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from lqe.models.adapters.indicator_rule_adapter import PRESETS

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC).timestamp()


def _ts(n: int, start: float = _EPOCH, step: float = 60.0) -> np.ndarray:
    return np.array([start + i * step for i in range(n)])


def _flat(n: int, price: float = 100.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    closes = np.full(n, price)
    return closes, closes + 0.5, closes - 0.5


# --- sleeve B: mean-reversion additions ----------------------------------


def test_keltner_reversion_goes_long_on_a_deep_atr_dip() -> None:
    closes, highs, lows = _flat(40)
    closes = closes.copy()
    highs = highs.copy()
    lows = lows.copy()
    closes[-1] = 90.0  # a sharp drop well outside a tight ATR channel
    highs[-1] = 90.5
    lows[-1] = 89.5
    target = PRESETS["keltner_reversion"](
        closes, highs, lows, _ts(len(closes)), {"window": 20, "n_atr": 2.0}
    )
    assert target == "LONG"


def test_keltner_reversion_is_flat_at_the_midline() -> None:
    closes, highs, lows = _flat(40)
    target = PRESETS["keltner_reversion"](
        closes, highs, lows, _ts(len(closes)), {"window": 20, "n_atr": 2.0}
    )
    assert target == "FLAT"


def test_ou_fairvalue_goes_long_on_a_deep_deviation() -> None:
    n = 80
    closes = np.full(n, 100.0)
    closes[-1] = 80.0  # far below the long-run EMA fair value
    highs, lows = closes + 0.5, closes - 0.5
    target = PRESETS["ou_fairvalue"](
        closes, highs, lows, _ts(n), {"window": 60, "entry_z": -1.5, "exit_z": 0.0}
    )
    assert target == "LONG"


def test_ou_fairvalue_is_flat_once_it_reverts_to_fair_value() -> None:
    closes, highs, lows = _flat(80)
    target = PRESETS["ou_fairvalue"](
        closes, highs, lows, _ts(len(closes)), {"window": 60, "entry_z": -1.5, "exit_z": 0.0}
    )
    assert target == "FLAT"


# --- sleeve E: volatility additions ---------------------------------------


def test_vol_mean_reversion_goes_long_on_a_vol_spike() -> None:
    rng = np.random.default_rng(3)
    calm = 100 + np.cumsum(rng.normal(0, 0.05, 40))
    spike = calm[-1] + np.cumsum(rng.normal(0, 2.0, 20))
    closes = np.concatenate([calm, spike])
    highs, lows = closes + 0.1, closes - 0.1
    target = PRESETS["vol_mean_reversion"](
        closes, highs, lows, _ts(len(closes)), {"window": 20, "spike_ratio": 1.5}
    )
    assert target == "LONG"


def test_vol_mean_reversion_is_flat_once_vol_normalizes() -> None:
    rng = np.random.default_rng(4)
    calm = 100 + np.cumsum(rng.normal(0, 0.05, 60))
    closes = calm
    highs, lows = closes + 0.1, closes - 0.1
    target = PRESETS["vol_mean_reversion"](
        closes, highs, lows, _ts(len(closes)), {"window": 20, "spike_ratio": 1.5}
    )
    assert target == "FLAT"


def test_vol_regime_gate_is_long_in_a_calm_regime() -> None:
    rng = np.random.default_rng(5)
    turbulent = 100 + np.cumsum(rng.normal(0, 2.0, 40))
    calm = turbulent[-1] + np.cumsum(rng.normal(0, 0.05, 20))
    closes = np.concatenate([turbulent, calm])
    highs, lows = closes + 0.1, closes - 0.1
    target = PRESETS["vol_regime_gate"](
        closes, highs, lows, _ts(len(closes)), {"window": 20, "calm_ratio": 1.2}
    )
    assert target == "LONG"


def test_vol_regime_gate_is_flat_in_a_turbulent_regime() -> None:
    rng = np.random.default_rng(6)
    calm = 100 + np.cumsum(rng.normal(0, 0.05, 40))
    turbulent = calm[-1] + np.cumsum(rng.normal(0, 2.0, 20))
    closes = np.concatenate([calm, turbulent])
    highs, lows = closes + 0.1, closes - 0.1
    target = PRESETS["vol_regime_gate"](
        closes, highs, lows, _ts(len(closes)), {"window": 20, "calm_ratio": 1.2}
    )
    assert target == "FLAT"


# --- sleeve G: breakout/structure ----------------------------------------


def test_opening_range_breakout_is_none_inside_the_opening_range() -> None:
    n = 10
    closes, highs, lows = _flat(n)
    target = PRESETS["opening_range_breakout"](
        closes, highs, lows, _ts(n), {"or_bars": 15}
    )
    assert target is None  # still inside today's own opening range


def test_opening_range_breakout_goes_long_on_a_break_above_the_range() -> None:
    # 15-bar opening range at 100, then a clear break above it later the
    # same UTC day (same day index, well within the 15-bar-per-minute window).
    n = 20
    closes = np.full(n, 100.0)
    closes[-1] = 105.0
    highs = closes + 0.5
    highs[:15] = 100.5  # the opening range's high stays capped at 100.5
    lows = closes - 0.5
    target = PRESETS["opening_range_breakout"](
        closes, highs, lows, _ts(n), {"or_bars": 15}
    )
    assert target == "LONG"


def test_support_resistance_range_fades_at_the_lower_edge() -> None:
    n = 25
    closes = np.full(n, 100.0)
    highs = closes + 1.0
    lows = closes - 1.0
    closes[-1] = 90.0  # a new low below the trailing N-bar range
    lows[-1] = 90.0
    target = PRESETS["support_resistance_range"](
        closes, highs, lows, _ts(n), {"lookback": 20}
    )
    assert target == "LONG"


def test_support_resistance_range_flattens_at_the_upper_edge() -> None:
    n = 25
    closes = np.full(n, 100.0)
    highs = closes + 1.0
    lows = closes - 1.0
    closes[-1] = 110.0  # a new high above the trailing N-bar range
    highs[-1] = 110.0
    target = PRESETS["support_resistance_range"](
        closes, highs, lows, _ts(n), {"lookback": 20}
    )
    assert target == "FLAT"


def test_squeeze_breakout_requires_a_genuine_squeeze_not_just_any_breakout() -> None:
    rng = np.random.default_rng(9)
    # a wide, choppy series (never squeezed) that still eventually breaks
    # a rolling Bollinger upper band -- should NOT fire without a squeeze.
    wide = 100 + np.cumsum(rng.normal(0, 1.5, 90))
    closes = wide
    highs, lows = closes + 0.2, closes - 0.2
    target = PRESETS["squeeze_breakout"](
        closes, highs, lows, _ts(len(closes)),
        {"window": 20, "n_std": 2.0, "squeeze_lookback": 60},
    )
    assert target != "LONG"


def test_squeeze_breakout_goes_long_right_as_a_real_squeeze_resolves_up() -> None:
    # a long, very tight calm period (genuine squeeze: band width sits at
    # its own multi-period low) followed by a sharp one-bar break above the
    # (still-narrow) upper band -- evaluated right at that breakout bar,
    # before the trend has had time to widen the bands back out again.
    calm = np.full(90, 100.0)
    closes = np.concatenate([calm, [108.0]])
    n = len(closes)
    highs, lows = closes + 0.05, closes - 0.05
    target = PRESETS["squeeze_breakout"](
        closes, highs, lows, _ts(n), {"window": 20, "n_std": 2.0, "squeeze_lookback": 60}
    )
    assert target == "LONG"


# --- sleeve H: seasonality/calendar ---------------------------------------


def test_time_of_day_is_long_inside_the_declared_hour_window() -> None:
    ts = datetime(2026, 3, 10, 15, 0, tzinfo=UTC).timestamp()  # 15:00 UTC
    target = PRESETS["time_of_day"](
        np.array([100.0]), np.array([100.0]), np.array([100.0]), np.array([ts]),
        {"start_hour": 13, "end_hour": 21},
    )
    assert target == "LONG"


def test_time_of_day_is_flat_outside_the_declared_hour_window() -> None:
    ts = datetime(2026, 3, 10, 3, 0, tzinfo=UTC).timestamp()  # 03:00 UTC
    target = PRESETS["time_of_day"](
        np.array([100.0]), np.array([100.0]), np.array([100.0]), np.array([ts]),
        {"start_hour": 13, "end_hour": 21},
    )
    assert target == "FLAT"


def test_day_of_week_is_long_on_a_weekday() -> None:
    ts = datetime(2026, 3, 10, tzinfo=UTC).timestamp()  # a Tuesday
    target = PRESETS["day_of_week"](
        np.array([100.0]), np.array([100.0]), np.array([100.0]), np.array([ts]), {}
    )
    assert target == "LONG"


def test_day_of_week_is_flat_on_a_weekend() -> None:
    ts = datetime(2026, 3, 14, tzinfo=UTC).timestamp()  # a Saturday
    target = PRESETS["day_of_week"](
        np.array([100.0]), np.array([100.0]), np.array([100.0]), np.array([ts]), {}
    )
    assert target == "FLAT"


def test_turn_of_month_is_long_near_the_month_boundary() -> None:
    ts = datetime(2026, 3, 1, tzinfo=UTC).timestamp()
    target = PRESETS["turn_of_month"](
        np.array([100.0]), np.array([100.0]), np.array([100.0]), np.array([ts]),
        {"window_days": 3},
    )
    assert target == "LONG"


def test_turn_of_month_is_flat_mid_month() -> None:
    ts = datetime(2026, 3, 15, tzinfo=UTC).timestamp()
    target = PRESETS["turn_of_month"](
        np.array([100.0]), np.array([100.0]), np.array([100.0]), np.array([ts]),
        {"window_days": 3},
    )
    assert target == "FLAT"
