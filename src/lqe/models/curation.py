"""Correlation-curation (docs/14 §3, v4): a redundancy check on top of
docs/03's original intake (`models/catalog.py::intake_check`). A model
earning a catalog slot is not just about permissive license + manifest
completeness + a real construction smoke-test -- it must also not be a
near-duplicate of a model already in the catalog. A diversified catalog
rejects the 40th trend clone; this is the function that says so.

This is deliberately a separate, composable check from `intake_check`
rather than folded into it: `intake_check` only ever needs a manifest +
factory (no market data), so it stays cheap and can run at import time.
Correlation curation needs aligned held-out return streams for both the
candidate and every existing model -- a real backtest result, not just a
constructibility check -- so callers run it as a second, explicit step once
those returns exist (e.g. after a walk-forward pass), not as part of the
catalog's registration path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class CurationResult:
    model_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    most_correlated_to: str | None = None
    correlation: float | None = None


def correlation_curation_check(
    *,
    candidate_id: str,
    candidate_returns: list[float],
    candidate_metric: float,
    existing_returns: dict[str, list[float]],
    existing_metrics: dict[str, float],
    redundancy_threshold: float = 0.7,
) -> CurationResult:
    """docs/14 §3: flag `candidate_id` as a redundant duplicate driver if its
    return-stream correlation to an existing model is >= `redundancy_threshold`
    **and** its `candidate_metric` (e.g. a held-out Sharpe/DSR) isn't
    strictly better than that existing model's own metric. High correlation
    alone doesn't quarantine a candidate -- a clearly-better version of an
    existing driver still earns its slot; only "redundant *and* not better"
    does, matching docs/14 §3's "if it's ~redundant and not clearly better."

    `existing_returns`/`existing_metrics` must share the same keys. An empty
    catalog (`existing_returns == {}`) always passes -- there is nothing to
    be redundant with yet.
    """
    if set(existing_returns) != set(existing_metrics):
        raise ValueError("existing_returns and existing_metrics must cover the same model ids")
    if not existing_returns:
        return CurationResult(model_id=candidate_id, passed=True)

    length = len(candidate_returns)
    if any(len(returns) != length for returns in existing_returns.values()):
        raise ValueError(
            "candidate and existing return streams must be aligned to the same length"
        )

    candidate_arr = np.asarray(candidate_returns, dtype=np.float64)
    worst_corr = 0.0
    worst_id: str | None = None
    for model_id, returns in existing_returns.items():
        existing_arr = np.asarray(returns, dtype=np.float64)
        corr = float(np.corrcoef(candidate_arr, existing_arr)[0, 1])
        if abs(corr) > abs(worst_corr):
            worst_corr = corr
            worst_id = model_id

    if worst_id is None:
        return CurationResult(model_id=candidate_id, passed=True)

    is_redundant = abs(worst_corr) >= redundancy_threshold
    is_clearly_better = candidate_metric > existing_metrics[worst_id]
    if is_redundant and not is_clearly_better:
        return CurationResult(
            model_id=candidate_id,
            passed=False,
            reasons=[
                f"correlation {worst_corr:.2f} to {worst_id!r} meets/exceeds the "
                f"{redundancy_threshold:.2f} redundancy threshold and its metric "
                f"({candidate_metric:.3f}) isn't better than {worst_id}'s "
                f"({existing_metrics[worst_id]:.3f}) -- quarantined as a duplicate driver"
            ],
            most_correlated_to=worst_id,
            correlation=worst_corr,
        )
    return CurationResult(
        model_id=candidate_id, passed=True,
        most_correlated_to=worst_id, correlation=worst_corr,
    )
