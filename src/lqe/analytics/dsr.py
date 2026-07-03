"""Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014), docs/archive/09
§9.7. Self-contained: the normal CDF uses `math.erf` and the inverse CDF
uses Acklam's rational approximation (accurate to ~1.15e-9) — no scipy
dependency for one function.

DSR is the probability the observed Sharpe ratio is genuinely positive
*after* deflating for having tried `n_trials` configurations on this data.
A high raw Sharpe from many trials can have a DSR near zero.
"""

from __future__ import annotations

import math

import numpy as np

_EULER_MASCHERONI = 0.5772156649015329


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's algorithm)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = (
        -3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
        1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
        6.680131188771972e01, -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
        -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
        3.754408661907416e00,
    )
    p_low = 0.02425
    p_high = 1 - p_low

    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        )
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


def _skewness(x: np.ndarray) -> float:
    n = len(x)
    std = float(np.std(x, ddof=0))
    if std == 0 or n < 3:
        return 0.0
    return float(np.mean(((x - np.mean(x)) / std) ** 3))


def _kurtosis(x: np.ndarray) -> float:
    """Non-excess kurtosis (a normal distribution scores 3.0)."""
    n = len(x)
    std = float(np.std(x, ddof=0))
    if std == 0 or n < 4:
        return 3.0
    return float(np.mean(((x - np.mean(x)) / std) ** 4))


def expected_max_sharpe(sharpe_std: float, n_trials: int) -> float:
    """E[max SR] across `n_trials` independent, genuinely skill-less trials."""
    if n_trials <= 1 or sharpe_std <= 0:
        return 0.0
    return sharpe_std * (
        (1 - _EULER_MASCHERONI) * norm_ppf(1 - 1.0 / n_trials)
        + _EULER_MASCHERONI * norm_ppf(1 - 1.0 / (n_trials * math.e))
    )


def probabilistic_sharpe_ratio(
    sharpe: float, benchmark_sharpe: float, n_obs: int, skew: float, kurtosis: float
) -> float:
    """PSR(SR*): probability the true Sharpe exceeds `benchmark_sharpe`."""
    if n_obs < 2:
        return 0.0
    denom = math.sqrt(max(1e-12, 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2))
    z = (sharpe - benchmark_sharpe) * math.sqrt(n_obs - 1) / denom
    return norm_cdf(z)


def deflated_sharpe_ratio(returns: np.ndarray, *, n_trials: int) -> float:
    n_obs = len(returns)
    if n_obs < 2 or n_trials < 1:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std == 0:
        return 0.0  # no variance at all is no evidence of skill, not a 50/50 boundary case
    sharpe = float(np.mean(returns) / std)
    skew = _skewness(returns)
    kurt = _kurtosis(returns)
    variance_term = max(1e-12, (1 - skew * sharpe + (kurt - 1) / 4 * sharpe**2) / max(1, n_obs - 1))
    sharpe_std = math.sqrt(variance_term)
    sr0 = expected_max_sharpe(sharpe_std, n_trials)
    return probabilistic_sharpe_ratio(sharpe, sr0, n_obs, skew, kurt)
