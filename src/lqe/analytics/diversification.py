"""Diversification score (docs/14 §1, v4): measures how genuinely
uncorrelated the *tracked/promoted* set is across return-driver sleeves --
not how many models exist. 50 trend variants in 50 costumes is one bet;
this module is what tells the difference between that and a real
diversification of drivers, computed on held-out return streams.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class DiversificationScore:
    n_models: int
    average_pairwise_correlation: float
    effective_number_of_bets: float
    n_sleeves: int
    dominant_sleeve: str
    max_sleeve_share: float


def pairwise_correlation_matrix(
    returns_by_model: dict[str, list[float]],
) -> tuple[list[str], npt.NDArray[np.float64]]:
    """`returns_by_model[id]` are aligned return streams (same bars, same
    length, held-out data per docs/14 §1) -- returns `(model_ids, corr)`
    where `corr[i][j]` is the Pearson correlation between model i and j.
    """
    ids = list(returns_by_model.keys())
    if len(ids) < 2:
        raise ValueError("need at least 2 models' return streams to compute correlation")
    lengths = {len(returns_by_model[mid]) for mid in ids}
    if len(lengths) != 1:
        raise ValueError("all return streams must be aligned to the same length")
    if next(iter(lengths)) < 2:
        raise ValueError("each return stream needs at least 2 observations")
    matrix = np.array([returns_by_model[mid] for mid in ids], dtype=np.float64)
    corr: npt.NDArray[np.float64] = np.asarray(np.corrcoef(matrix), dtype=np.float64)
    return ids, corr


def average_pairwise_correlation(corr: npt.NDArray[np.float64]) -> float:
    """Mean of the off-diagonal (upper-triangle) entries -- docs/14 §1's
    "average pairwise correlation of the promoted/tracked models" metric.
    Target: low (e.g. < ~0.3 median across sleeves)."""
    n = corr.shape[0]
    if n < 2:
        raise ValueError("need at least 2 models to average a pairwise correlation")
    iu = np.triu_indices(n, k=1)
    return float(np.mean(corr[iu]))


def effective_number_of_bets(corr: npt.NDArray[np.float64]) -> float:
    """docs/14 §1's "effective number of bets (via an eigenvalue ... measure)"
    -- (sum of eigenvalues)^2 / sum(eigenvalues^2) of the correlation matrix.
    Equals N when every stream is uncorrelated (all eigenvalues 1); equals 1
    when every stream is identical (one eigenvalue N, rest 0). This is the
    real headline the milestone asks for, not "N models added."
    """
    eigenvalues = np.linalg.eigvalsh(corr)
    # numerical noise on a near-singular matrix can produce tiny negatives;
    # true eigenvalues of a correlation matrix are never negative.
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    total = float(eigenvalues.sum())
    if total <= 0:
        return 0.0
    return (total**2) / float(np.sum(eigenvalues**2))


def sleeve_distribution(sleeve_by_model: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sleeve in sleeve_by_model.values():
        counts[sleeve] = counts.get(sleeve, 0) + 1
    return counts


def max_sleeve_share(sleeve_by_model: dict[str, str]) -> tuple[str, float]:
    """docs/14 §7's "no single sleeve dominating" acceptance criterion --
    the sleeve with the most models and its share of the total."""
    if not sleeve_by_model:
        raise ValueError("no models to compute a sleeve share over")
    counts = sleeve_distribution(sleeve_by_model)
    total = sum(counts.values())
    dominant = max(counts, key=lambda sleeve: counts[sleeve])
    return dominant, counts[dominant] / total


def diversification_score(
    returns_by_model: dict[str, list[float]], sleeve_by_model: dict[str, str]
) -> DiversificationScore:
    """docs/14 §1's acceptance metric, bundled: average pairwise correlation
    (lower is better), effective number of bets (higher is better -- the
    real headline vs. "N models added"), sleeve count, and whether one
    sleeve dominates. Callers should compute this over the tracked/promoted
    set on held-out returns, per docs/14 §1/§7.
    """
    if set(returns_by_model) != set(sleeve_by_model):
        raise ValueError("returns_by_model and sleeve_by_model must cover the same model ids")
    ids, corr = pairwise_correlation_matrix(returns_by_model)
    scoped_sleeves = {mid: sleeve_by_model[mid] for mid in ids}
    dominant, share = max_sleeve_share(scoped_sleeves)
    return DiversificationScore(
        n_models=len(ids),
        average_pairwise_correlation=average_pairwise_correlation(corr),
        effective_number_of_bets=effective_number_of_bets(corr),
        n_sleeves=len(sleeve_distribution(scoped_sleeves)),
        dominant_sleeve=dominant,
        max_sleeve_share=share,
    )
