"""Self-contained numpy performance metrics (docs/archive/09 §9.6).

Report all, worship none: no single number is treated as the answer —
`Metrics` is the evidence a human/gate reads together with sample size and
cost assumptions, never a raw P&L headline.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict


class Metrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    n_periods: int
    n_trades: int
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    max_drawdown_duration: int
    calmar: float
    turnover: float
    hit_rate: float
    payoff_ratio: float
    tail_ratio: float


def returns_from_equity(equity_curve: Sequence[Decimal]) -> npt.NDArray[np.float64]:
    equity = np.array([float(e) for e in equity_curve], dtype=np.float64)
    if len(equity) < 2:
        return np.array([], dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.diff(equity) / equity[:-1]
    return np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)


def sharpe_ratio(returns: npt.NDArray[np.float64], *, periods_per_year: float) -> float:
    if len(returns) < 2 or np.std(returns, ddof=1) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(periods_per_year))


def sortino_ratio(returns: npt.NDArray[np.float64], *, periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    downside_std = np.std(downside, ddof=1) if len(downside) > 1 else 0.0
    if downside_std == 0:
        return 0.0
    return float(np.mean(returns) / downside_std * np.sqrt(periods_per_year))


def max_drawdown(equity_curve: Sequence[Decimal]) -> tuple[float, int]:
    """Returns (max drawdown as a positive fraction, duration in bars)."""
    equity = np.array([float(e) for e in equity_curve], dtype=np.float64)
    if len(equity) == 0:
        return 0.0, 0
    running_peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.nan_to_num((running_peak - equity) / running_peak, nan=0.0)
    worst = float(np.max(drawdown)) if len(drawdown) else 0.0

    duration = 0
    longest = 0
    for value in drawdown:
        if value > 0:
            duration += 1
            longest = max(longest, duration)
        else:
            duration = 0
    return worst, longest


def cagr(equity_curve: Sequence[Decimal], *, periods_per_year: float) -> float:
    """Annualized return. A sample much shorter than one "year" of
    `periods_per_year` (e.g. a few hundred 1-minute bars) makes this
    extrapolation extreme by construction — that's expected, not a bug; the
    gate's min_periods threshold is what actually protects against
    over-trusting a too-short sample, not this function softening the math."""
    equity = np.array([float(e) for e in equity_curve], dtype=np.float64)
    if len(equity) < 2 or equity[0] <= 0:
        return 0.0
    n_periods = len(equity) - 1
    years = n_periods / periods_per_year
    if years <= 0:
        return 0.0
    total_return = equity[-1] / equity[0]
    if total_return <= 0:
        return -1.0
    with np.errstate(over="ignore"):
        result = total_return ** (1 / years) - 1
    if not np.isfinite(result):
        return math.copysign(1e12, result)
    return float(result)


def calmar_ratio(cagr_value: float, max_dd: float) -> float:
    if max_dd == 0:
        return 0.0
    return cagr_value / max_dd


def hit_rate(trade_pnls: Sequence[float]) -> float:
    if not trade_pnls:
        return 0.0
    wins = sum(1 for p in trade_pnls if p > 0)
    return wins / len(trade_pnls)


def payoff_ratio(trade_pnls: Sequence[float]) -> float:
    wins = [p for p in trade_pnls if p > 0]
    losses = [abs(p) for p in trade_pnls if p < 0]
    if not wins or not losses:
        return 0.0
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    if avg_loss == 0:
        return 0.0
    return avg_win / avg_loss


def tail_ratio(returns: npt.NDArray[np.float64]) -> float:
    if len(returns) < 20:
        return 0.0
    right = np.percentile(returns, 95)
    left = np.percentile(returns, 5)
    if left == 0:
        return 0.0
    return float(abs(right / left))


def turnover(trade_notionals: Sequence[Decimal], *, avg_equity: Decimal) -> float:
    if avg_equity <= 0 or not trade_notionals:
        return 0.0
    total = sum((float(n) for n in trade_notionals), 0.0)
    return total / float(avg_equity)


def compute_metrics(
    *,
    equity_curve: Sequence[Decimal],
    trade_pnls: Sequence[float],
    trade_notionals: Sequence[Decimal],
    periods_per_year: float,
) -> Metrics:
    returns = returns_from_equity(equity_curve)
    dd, dd_duration = max_drawdown(equity_curve)
    cagr_value = cagr(equity_curve, periods_per_year=periods_per_year)
    avg_equity = (
        Decimal(sum(equity_curve, Decimal("0"))) / Decimal(len(equity_curve))
        if equity_curve
        else Decimal("0")
    )
    return Metrics(
        n_periods=len(equity_curve),
        n_trades=len(trade_pnls),
        cagr=cagr_value,
        sharpe=sharpe_ratio(returns, periods_per_year=periods_per_year),
        sortino=sortino_ratio(returns, periods_per_year=periods_per_year),
        max_drawdown=dd,
        max_drawdown_duration=dd_duration,
        calmar=calmar_ratio(cagr_value, dd),
        turnover=turnover(trade_notionals, avg_equity=avg_equity),
        hit_rate=hit_rate(trade_pnls),
        payoff_ratio=payoff_ratio(trade_pnls),
        tail_ratio=tail_ratio(returns),
    )
