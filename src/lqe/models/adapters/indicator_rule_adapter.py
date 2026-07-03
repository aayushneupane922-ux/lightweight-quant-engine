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

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.models.adapters.indicators import adx, bollinger, donchian, macd, rsi, sma

Arr = npt.NDArray[np.float64]
TargetState = Literal["LONG", "FLAT"] | None
PresetFn = Callable[[Arr, Arr, Arr, dict[str, float]], TargetState]


def _preset_macd_trend(
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
) -> TargetState:
    lookback = int(params.get("lookback", 90))
    if len(closes) <= lookback:
        return None
    trailing_return = (closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1]
    return "LONG" if trailing_return > 0 else "FLAT"


def _preset_roc_momentum(
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
    closes: Arr, highs: Arr, lows: Arr, params: dict[str, float]
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
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._highs.clear()
        self._lows.clear()
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        self._highs.append(float(ev.h))
        self._lows.append(float(ev.l))

        # self.params is dict[str, object] per the Strategy protocol; every
        # preset here only ever reads numeric values out of it.
        target = self._preset_fn(
            np.array(self._closes),
            np.array(self._highs),
            np.array(self._lows),
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
