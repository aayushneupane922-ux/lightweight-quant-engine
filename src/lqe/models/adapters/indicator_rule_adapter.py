"""`IndicatorRuleAdapter`: one adapter unlocks a whole family through
config, not N files (docs/03 §3.3/§3.4, docs/archive/30 §30.3). The native
(numpy-only) equivalent of the originally-planned `PandasTaRuleAdapter` —
see `indicators.py`'s docstring and `pyproject.toml` for why pandas-ta was
dropped.

Each preset is a pure function `(closes, highs, lows, params) -> target
state`: `"LONG"` (should be long), `"FLAT"` (should be flat), or `None`
(not enough data yet, or inside a neutral zone — hold whatever state the
position is already in). The adapter itself only handles the generic
ENTER/EXIT transition bookkeeping, matching `trend_ma_cross`'s own pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import numpy as np
import numpy.typing as npt

from lqe.constants import ADAPTER_HISTORY_CAP
from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.models.adapters.indicators import adx, atr, bollinger, donchian, ema, macd, rsi, sma

Arr = npt.NDArray[np.float64]
TargetState = Literal["LONG", "FLAT"] | None
# `timestamps` is each bar's `ts_open` as a Unix epoch-seconds float -- only
# the calendar/seasonality presets (docs/14 sleeve H) use it; every other
# preset ignores the parameter. Threading it through every preset (rather
# than a second adapter class) keeps one adapter, one dispatch path.
PresetFn = Callable[[Arr, Arr, Arr, Arr, dict[str, float]], TargetState]


def _preset_macd_trend(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    signal_span = int(params.get("signal", 9))
    if len(closes) < slow + signal_span:
        return None
    macd_line, signal_line, _ = macd(closes, fast=fast, slow=slow, signal=signal_span)
    if np.isnan(macd_line[-1]) or np.isnan(signal_line[-1]):
        return None
    return "LONG" if macd_line[-1] > signal_line[-1] else "FLAT"


def _preset_donchian_breakout(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    lookback = int(params.get("lookback", 20))
    if len(closes) <= lookback:
        return None
    upper, lower = donchian(highs, lows, lookback)
    if np.isnan(upper[-1]) or np.isnan(lower[-1]):
        return None
    price = closes[-1]
    if price >= upper[-1]:
        return "LONG"
    if price <= lower[-1]:
        return "FLAT"
    return None


def _preset_adx_trend(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    fast = int(params.get("fast", 10))
    slow = int(params.get("slow", 30))
    adx_window = int(params.get("adx_window", 14))
    adx_threshold = params.get("adx_threshold", 25.0)
    if len(closes) < max(slow, 2 * adx_window + 1):
        return None
    fast_ma, slow_ma = sma(closes, fast)[-1], sma(closes, slow)[-1]
    adx_val = adx(highs, lows, closes, adx_window)[-1]
    if np.isnan(fast_ma) or np.isnan(slow_ma) or np.isnan(adx_val):
        return None
    if adx_val < adx_threshold:
        return "FLAT"  # not trending -> stand aside regardless of MA position
    return "LONG" if fast_ma > slow_ma else "FLAT"


def _preset_tsmom(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    lookback = int(params.get("lookback", 90))
    if len(closes) <= lookback:
        return None
    trailing_return = (closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1]
    return "LONG" if trailing_return > 0 else "FLAT"


def _preset_roc_momentum(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    lookback = int(params.get("lookback", 20))
    threshold = params.get("threshold", 0.0)
    if len(closes) <= lookback:
        return None
    roc = (closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1]
    if roc > threshold:
        return "LONG"
    if roc <= 0:
        return "FLAT"
    return None


def _preset_zscore_reversion(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    window = int(params.get("window", 20))
    entry_z = params.get("entry_z", -2.0)
    exit_z = params.get("exit_z", 0.0)
    if len(closes) < window:
        return None
    tail = closes[-window:]
    std = np.std(tail)
    if std == 0:
        return None
    z = (closes[-1] - np.mean(tail)) / std
    if z <= entry_z:
        return "LONG"
    if z >= exit_z:
        return "FLAT"
    return None


def _preset_bollinger_fade(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    window = int(params.get("window", 20))
    n_std = params.get("n_std", 2.0)
    if len(closes) < window:
        return None
    mid, _, lower = bollinger(closes, window=window, n_std=n_std)
    if np.isnan(mid[-1]) or np.isnan(lower[-1]):
        return None
    price = closes[-1]
    if price <= lower[-1]:
        return "LONG"
    if price >= mid[-1]:
        return "FLAT"
    return None


def _preset_rsi_fade(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    window = int(params.get("window", 14))
    oversold = params.get("oversold", 30.0)
    overbought = params.get("overbought", 70.0)
    if len(closes) < window + 1:
        return None
    value = rsi(closes, window)[-1]
    if np.isnan(value):
        return None
    if value <= oversold:
        return "LONG"
    if value >= overbought:
        return "FLAT"
    return None


def _preset_vol_breakout(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    window = int(params.get("window", 20))
    expansion_ratio = params.get("expansion_ratio", 1.5)
    if len(closes) < window * 2 + 1:
        return None
    returns = np.diff(closes) / closes[:-1]
    recent_vol = np.std(returns[-window:])
    baseline_vol = np.std(returns[-2 * window : -window])
    if baseline_vol == 0:
        return None
    if recent_vol >= expansion_ratio * baseline_vol:
        return "LONG"
    if recent_vol < baseline_vol:
        return "FLAT"
    return None


def _preset_keltner_reversion(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve B: an ATR-scaled channel fade, distinct from
    # bollinger_fade's rolling-std band -- ATR reacts to true range (gaps,
    # wicks), not just closes, so the two bands diverge in gappy markets.
    window = int(params.get("window", 20))
    n_atr = params.get("n_atr", 2.0)
    if len(closes) < window + 1:
        return None
    mid = sma(closes, window)
    band = atr(highs, lows, closes, window)
    if np.isnan(mid[-1]) or np.isnan(band[-1]):
        return None
    lower = mid[-1] - n_atr * band[-1]
    price = closes[-1]
    if price <= lower:
        return "LONG"
    if price >= mid[-1]:
        return "FLAT"
    return None


def _preset_ou_fairvalue(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve B: an Ornstein-Uhlenbeck-style fair-value fade -- an
    # EMA fair value (reacts faster than zscore_reversion's SMA) plus a
    # long-run rolling-std deviation, on its own (longer, by default)
    # window so it's a genuinely different fair-value estimate, not a
    # renamed zscore_reversion.
    window = int(params.get("window", 60))
    entry_z = params.get("entry_z", -1.5)
    exit_z = params.get("exit_z", 0.0)
    if len(closes) < window:
        return None
    fair_value = ema(closes, window)
    tail = closes[-window:]
    std = np.std(tail)
    if np.isnan(fair_value[-1]):
        return None
    # a flat/zero-dispersion tail has no meaningful z-score, but price is by
    # definition sitting exactly at fair value in that case -- FLAT, not
    # "not enough data yet."
    deviation = 0.0 if std == 0 else (closes[-1] - fair_value[-1]) / std
    if deviation <= entry_z:
        return "LONG"
    if deviation >= exit_z:
        return "FLAT"
    return None


def _preset_vol_mean_reversion(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve E: "vol mean-reversion (vol-of-vol)" -- fades a vol
    # SPIKE back toward its own baseline (opposite bet from vol_breakout,
    # which rides an expansion). Trades the underlying long while recent
    # vol is elevated vs. its own longer-run level, flat once it normalizes.
    window = int(params.get("window", 20))
    spike_ratio = params.get("spike_ratio", 1.5)
    if len(closes) < window * 2 + 1:
        return None
    returns = np.diff(closes) / closes[:-1]
    recent_vol = np.std(returns[-window:])
    baseline_vol = np.std(returns[-2 * window : -window])
    if baseline_vol == 0:
        return None
    if recent_vol >= spike_ratio * baseline_vol:
        return "LONG"
    if recent_vol <= baseline_vol:
        return "FLAT"
    return None


def _preset_vol_regime_gate(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve I: a regime *overlay* -- long only while realized vol
    # is calm (a "trending/tradeable" regime proxy), flat once it turns
    # turbulent, regardless of price direction. A pure regime switch, not a
    # directional bet, which is what makes it a genuinely different sleeve
    # from the trend/mean-reversion signals it could gate.
    window = int(params.get("window", 20))
    calm_ratio = params.get("calm_ratio", 1.2)
    if len(closes) < window * 2 + 1:
        return None
    returns = np.diff(closes) / closes[:-1]
    recent_vol = np.std(returns[-window:])
    baseline_vol = np.std(returns[-2 * window : -window])
    if baseline_vol == 0:
        return None
    if recent_vol <= baseline_vol:
        return "LONG"
    if recent_vol >= calm_ratio * baseline_vol:
        return "FLAT"
    return None


def _preset_opening_range_breakout(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve G: a per-session (UTC calendar day) opening range --
    # the first `or_bars` bars of each day set that day's range; a later
    # close above it is a breakout long, below the range midpoint is flat.
    or_bars = int(params.get("or_bars", 15))
    if len(timestamps) < or_bars + 1 or np.isnan(timestamps[-1]):
        return None
    day_index = (timestamps // 86400).astype(np.int64)
    today = day_index[-1]
    todays_bars = np.flatnonzero(day_index == today)
    if len(todays_bars) <= or_bars:
        return None  # still inside (or before) today's own opening range
    opening = todays_bars[:or_bars]
    or_high = float(np.max(highs[opening]))
    or_low = float(np.min(lows[opening]))
    price = closes[-1]
    if price > or_high:
        return "LONG"
    if price <= (or_high + or_low) / 2:
        return "FLAT"
    return None


def _preset_support_resistance_range(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve G: the *fade* twin of donchian_breakout -- the same
    # N-bar swing high/low, but bought near support and flattened near
    # resistance instead of bought on a breakout past either edge.
    lookback = int(params.get("lookback", 20))
    if len(closes) <= lookback:
        return None
    upper, lower = donchian(highs, lows, lookback)
    if np.isnan(upper[-1]) or np.isnan(lower[-1]):
        return None
    price = closes[-1]
    if price <= lower[-1]:
        return "LONG"
    if price >= upper[-1]:
        return "FLAT"
    return None


def _preset_squeeze_breakout(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve G: "squeeze / vol-contraction breakout" -- long only
    # when a genuine squeeze (Bollinger band width near a multi-period low)
    # resolves upward through the upper band, distinguishing it from
    # vol_breakout (which reacts to realized-return vol, not band width)
    # and from plain donchian_breakout (which has no squeeze precondition).
    window = int(params.get("window", 20))
    n_std = params.get("n_std", 2.0)
    squeeze_lookback = int(params.get("squeeze_lookback", 60))
    if len(closes) < window + squeeze_lookback + 1:
        return None
    mid, upper, lower = bollinger(closes, window=window, n_std=n_std)
    if np.isnan(mid[-1]) or np.isnan(upper[-2]) or np.isnan(lower[-2]):
        return None
    # the squeeze/breakout reference is *yesterday's* band -- today's own
    # rolling window already has today's breakout price baked into it,
    # which would make "today's width" look artificially wide right at the
    # moment it should read as squeezed.
    width = upper - lower
    recent_width = width[-squeeze_lookback - 1 : -1]
    valid = recent_width[~np.isnan(recent_width)]
    if len(valid) < squeeze_lookback // 2:
        return None
    was_squeezed = width[-2] <= np.percentile(valid, 25)
    price = closes[-1]
    if was_squeezed and price > upper[-2]:
        return "LONG"
    if price < mid[-1]:
        return "FLAT"
    return None


def _preset_time_of_day(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve H: a pure calendar effect -- long only during a
    # declared UTC hour window, flat the rest of the day. No price input
    # at all, by design (this is the "hour effects" seasonality bet, not a
    # technical rule).
    if len(timestamps) == 0 or np.isnan(timestamps[-1]):
        return None
    start_hour = int(params.get("start_hour", 13))  # US session open, UTC
    end_hour = int(params.get("end_hour", 21))
    hour = int((timestamps[-1] // 3600) % 24)
    if start_hour <= hour < end_hour:
        return "LONG"
    return "FLAT"


def _preset_day_of_week(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve H: long on weekdays, flat over the weekend -- crypto's
    # well-documented lower weekend liquidity/participation effect.
    if len(timestamps) == 0 or np.isnan(timestamps[-1]):
        return None
    # 1970-01-01 (epoch 0) was a Thursday -> weekday 0=Mon .. 6=Sun via +3 shift
    weekday = int((timestamps[-1] // 86400 + 3) % 7)
    long_weekdays = {0, 1, 2, 3, 4}  # Mon-Fri
    return "LONG" if weekday in long_weekdays else "FLAT"


def _preset_turn_of_month(
    closes: Arr, highs: Arr, lows: Arr, timestamps: Arr, params: dict[str, float]
) -> TargetState:
    # docs/14 sleeve H: long during the declared last-N/first-N calendar
    # days of the month (the turn-of-month effect), flat mid-month.
    if len(timestamps) == 0 or np.isnan(timestamps[-1]):
        return None
    window_days = int(params.get("window_days", 3))
    day_of_month = _day_of_month(timestamps[-1])
    days_in_month = _days_in_month(timestamps[-1])
    if day_of_month <= window_days or day_of_month > days_in_month - window_days:
        return "LONG"
    return "FLAT"


def _day_of_month(epoch_seconds: float) -> int:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch_seconds, tz=UTC).day


def _days_in_month(epoch_seconds: float) -> int:
    import calendar
    from datetime import UTC, datetime

    dt = datetime.fromtimestamp(epoch_seconds, tz=UTC)
    return calendar.monthrange(dt.year, dt.month)[1]


PRESETS: dict[str, PresetFn] = {
    "macd_trend": _preset_macd_trend,
    "donchian_breakout": _preset_donchian_breakout,
    "adx_trend": _preset_adx_trend,
    "tsmom": _preset_tsmom,
    "roc_momentum": _preset_roc_momentum,
    "zscore_reversion": _preset_zscore_reversion,
    "bollinger_fade": _preset_bollinger_fade,
    "rsi_fade": _preset_rsi_fade,
    "vol_breakout": _preset_vol_breakout,
    "keltner_reversion": _preset_keltner_reversion,
    "ou_fairvalue": _preset_ou_fairvalue,
    "vol_mean_reversion": _preset_vol_mean_reversion,
    "vol_regime_gate": _preset_vol_regime_gate,
    "opening_range_breakout": _preset_opening_range_breakout,
    "support_resistance_range": _preset_support_resistance_range,
    "squeeze_breakout": _preset_squeeze_breakout,
    "time_of_day": _preset_time_of_day,
    "day_of_week": _preset_day_of_week,
    "turn_of_month": _preset_turn_of_month,
}


class IndicatorRuleAdapter:
    def __init__(self, *, symbol: Symbol, preset: str, name: str, params: dict[str, float]) -> None:
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}; available: {sorted(PRESETS)}")
        self.name = name
        self.params: dict[str, object] = dict(params)
        self._symbol = symbol
        self._preset_fn = PRESETS[preset]
        self._closes: list[float] = []
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._timestamps: list[float] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._highs.clear()
        self._lows.clear()
        self._timestamps.clear()
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        self._highs.append(float(ev.h))
        self._lows.append(float(ev.l))
        self._timestamps.append(ev.ts_open.timestamp())
        # Bound the raw history (perf phase 3c) so the per-bar full-window
        # recompute below stays O(ADAPTER_HISTORY_CAP), not O(session).
        # Trimmed at 2x the cap (amortized O(1)); every preset's real
        # lookback fits well inside the cap -- see constants.py.
        if len(self._closes) > 2 * ADAPTER_HISTORY_CAP:
            del self._closes[: -ADAPTER_HISTORY_CAP]
            del self._highs[: -ADAPTER_HISTORY_CAP]
            del self._lows[: -ADAPTER_HISTORY_CAP]
            del self._timestamps[: -ADAPTER_HISTORY_CAP]

        # self.params is dict[str, object] per the Strategy protocol; every
        # preset here only ever reads numeric values out of it.
        target = self._preset_fn(
            np.array(self._closes),
            np.array(self._highs),
            np.array(self._lows),
            np.array(self._timestamps),
            self.params,  # type: ignore[arg-type]
        )
        if target is None or target == self._position:
            return []

        if target == "LONG":
            self._position = "LONG"
            return [
                SignalEvent(
                    strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                    intent_kind="ENTER", bar_ts=ev.ts_open, reason=f"{self.name}: target=LONG",
                )
            ]
        self._position = "FLAT"
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction="FLAT", strength=0.0,
                intent_kind="EXIT", bar_ts=ev.ts_open, reason=f"{self.name}: target=FLAT",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
