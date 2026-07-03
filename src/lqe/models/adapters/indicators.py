"""Native (numpy-only) technical indicators — "own" per docs/03's manifest
license convention. Built in place of `pandas-ta`: pandas-ta itself is MIT,
but it hard-requires `tqdm`, which is dual-licensed MPL-2.0/MIT with the
bulk of its files under MPL-2.0 (weak copyleft) — not on the MIT/BSD/
Apache/NCSA allowlist (CLAUDE.md non-negotiable #8). These are simple,
well-known formulas; owning them outright avoids the dependency-license
question entirely and keeps every line auditable.

Every function is a pure, deterministic transform over a numpy array of
closes (or high/low/close) — no state, no I/O, safe to call from a
`Strategy.on_market` at any bar.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def sma(values: npt.NDArray[np.float64], window: int) -> npt.NDArray[np.float64]:
    """Simple moving average. First `window - 1` entries are NaN."""
    if window < 1:
        raise ValueError("window must be >= 1")
    out = np.full(len(values), np.nan)
    if len(values) < window:
        return out
    cumsum = np.cumsum(np.insert(values, 0, 0.0))
    out[window - 1 :] = (cumsum[window:] - cumsum[:-window]) / window
    return out


def ema(values: npt.NDArray[np.float64], span: int) -> npt.NDArray[np.float64]:
    """Exponential moving average, seeded with the SMA of the first `span`
    values (a standard, deterministic convention)."""
    if span < 1:
        raise ValueError("span must be >= 1")
    out = np.full(len(values), np.nan)
    if len(values) < span:
        return out
    alpha = 2.0 / (span + 1.0)
    out[span - 1] = np.mean(values[:span])
    for i in range(span, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(values: npt.NDArray[np.float64], window: int) -> npt.NDArray[np.float64]:
    """Wilder's RSI (0-100)."""
    if window < 1:
        raise ValueError("window must be >= 1")
    out = np.full(len(values), np.nan)
    if len(values) < window + 1:
        return out
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:window])
    avg_loss = np.mean(losses[:window])
    out[window] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(window, len(deltas)):
        avg_gain = (avg_gain * (window - 1) + gains[i]) / window
        avg_loss = (avg_loss * (window - 1) + losses[i]) / window
        out[i + 1] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: npt.NDArray[np.float64], *, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line = fast_ema - slow_ema
    valid = ~np.isnan(macd_line)
    signal_line = np.full(len(values), np.nan)
    if valid.any():
        first_valid = int(np.argmax(valid))
        signal_line[first_valid:] = ema(macd_line[first_valid:], signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(
    values: npt.NDArray[np.float64], *, window: int = 20, n_std: float = 2.0
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Returns (mid, upper, lower)."""
    mid = sma(values, window)
    rolling_std = np.full(len(values), np.nan)
    for i in range(window - 1, len(values)):
        rolling_std[i] = np.std(values[i - window + 1 : i + 1], ddof=0)
    upper = mid + n_std * rolling_std
    lower = mid - n_std * rolling_std
    return mid, upper, lower


def donchian(
    high: npt.NDArray[np.float64], low: npt.NDArray[np.float64], window: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Returns (upper_channel, lower_channel), each the trailing high/low
    over `window` bars *excluding* the current bar (so a breakout check
    against the current bar's price is never comparing a bar to itself)."""
    upper = np.full(len(high), np.nan)
    lower = np.full(len(low), np.nan)
    for i in range(window, len(high)):
        upper[i] = np.max(high[i - window : i])
        lower[i] = np.min(low[i - window : i])
    return upper, lower


def _wilder_smooth(values: npt.NDArray[np.float64], window: int) -> npt.NDArray[np.float64]:
    """Wilder's smoothing (the specific EMA variant ADX/RSI use), seeded by
    a simple average of the first `window` values."""
    out = np.full(len(values), np.nan)
    if len(values) < window:
        return out
    out[window - 1] = np.mean(values[:window])
    for i in range(window, len(values)):
        out[i] = (out[i - 1] * (window - 1) + values[i]) / window
    return out


def adx(
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    window: int = 14,
) -> npt.NDArray[np.float64]:
    """Average Directional Index (Wilder). Measures trend *strength*, not
    direction — used to gate other signals to trending regimes."""
    n = len(close)
    if n < 2 * window + 1:
        return np.full(n, np.nan)

    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = close[:-1]
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - prev_close), np.abs(low[1:] - prev_close)),
    )

    smoothed_tr = _wilder_smooth(tr, window)
    smoothed_plus_dm = _wilder_smooth(plus_dm, window)
    smoothed_minus_dm = _wilder_smooth(minus_dm, window)

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * smoothed_plus_dm / smoothed_tr
        minus_di = 100.0 * smoothed_minus_dm / smoothed_tr
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    dx = np.nan_to_num(dx, nan=0.0)

    adx_values = _wilder_smooth(dx, window)
    # dx/adx_values are computed over close[1:] (length n-1); shift back by
    # one to align with close's own indexing.
    out = np.full(n, np.nan)
    out[1:] = adx_values
    return out
