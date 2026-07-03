"""Probability of Backtest Overfitting via combinatorially-symmetric
cross-validation (Bailey, Borwein, Lopez de Prado & Zhu, 2015),
docs/archive/09 §9.7.

Needs a returns matrix across *multiple* candidate configs to mean
anything — PBO answers "given how many configs I tried, how likely is it
that the in-sample winner is actually below-median out-of-sample?" With
only one config tried, there was no search to overfit; callers should
treat PBO as 0.0 (not applicable) in that case rather than call this.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import numpy.typing as npt


def probability_of_backtest_overfitting(
    returns_matrix: npt.NDArray[np.float64], *, n_splits: int = 8
) -> float:
    """`returns_matrix`: shape (T, N) — T periods, N candidate configs."""
    if returns_matrix.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (periods, configs)")
    t, n = returns_matrix.shape
    if n < 2:
        raise ValueError("PBO needs at least 2 candidate configs to compare")
    if n_splits % 2 != 0 or n_splits < 2:
        raise ValueError("n_splits must be even and >= 2")
    block_size = t // n_splits
    if block_size < 1:
        raise ValueError(f"not enough periods ({t}) for {n_splits} splits")

    blocks = [returns_matrix[i * block_size : (i + 1) * block_size] for i in range(n_splits)]
    half = n_splits // 2

    logits: list[float] = []
    for is_indices in itertools.combinations(range(n_splits), half):
        oos_indices = [i for i in range(n_splits) if i not in is_indices]
        is_returns = np.concatenate([blocks[i] for i in is_indices], axis=0)
        oos_returns = np.concatenate([blocks[i] for i in oos_indices], axis=0)

        is_sharpe = _sharpe_per_column(is_returns)
        oos_sharpe = _sharpe_per_column(oos_returns)

        best_is = int(np.argmax(is_sharpe))
        rank = int(np.sum(oos_sharpe < oos_sharpe[best_is])) + 1  # 1-indexed, from the bottom
        omega = rank / (n + 1)
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1 - omega)))

    return float(np.mean(np.array(logits) <= 0))


def _sharpe_per_column(returns: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    std = np.std(returns, axis=0, ddof=1)
    mean = np.mean(returns, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = np.where(std > 0, mean / std, 0.0)
    return np.asarray(sharpe)
