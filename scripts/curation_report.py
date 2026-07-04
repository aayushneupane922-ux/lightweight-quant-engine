"""docs/14 §3 (v4): operationalize `models/curation.py::correlation_curation_check`
against the real, full 104-model catalog's actual backtested returns --
closing the "not yet wired into a live pipeline" open question left since
M23 (`f25b60b`).

    python scripts/curation_report.py

`correlation_curation_check` is deliberately a pure, composable function
(docs/14 §3's own design) rather than something invoked inside
`build_scaled_catalog()` itself -- that function stays cheap/import-time
by construction, with no market data available at registration time. The
real "pipeline" this belongs in is a **pre-admission check for a new
candidate model**: before adding model N+1 to the catalog, backtest it
and every already-admitted model on the same reference data, then call
this function. This script simulates exactly that, walking the existing
104-model catalog in its own registration order and checking each model
against every model registered *before* it -- i.e. "if correlation
curation had been enforced from the start, which models would it have
flagged as redundant duplicates?"

Honesty notes:
- Same synthetic multi-symbol bar stream as `diversification_report.py`
  (not real market data) -- this measures the *shape* of redundancy in
  the catalog's design, not live edge.
- `candidate_metric` here is a simple Sharpe-like ratio (mean/std of
  per-bar returns) on the same synthetic backtest -- a real pipeline would
  use a proper held-out walk-forward DSR, but this is enough to exercise
  the "redundant AND not clearly better" logic for real, not just in a
  synthetic unit test.
- Models that never traded this window (zero-variance returns) are
  skipped -- correlation is undefined for a constant series -- and
  reported separately, same as `diversification_report.py`.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
from diversification_report import N_BARS, SYMBOL, _bar_returns, _synthetic_multi_symbol_bars

from lqe.backtest.runner import run_backtest
from lqe.models.catalog_scale import build_scaled_catalog
from lqe.models.curation import correlation_curation_check


def _sharpe_like(returns: list[float]) -> float:
    std = float(np.std(returns))
    return float(np.mean(returns)) / std if std > 0 else 0.0


def main() -> int:
    bars = _synthetic_multi_symbol_bars(N_BARS)
    catalog, _ = build_scaled_catalog(SYMBOL)
    entries = catalog.all()  # already in registration order
    print(f"running correlation curation over {len(entries)} models, in registration order...")

    returns_by_model: dict[str, list[float]] = {}
    metric_by_model: dict[str, float] = {}
    inert: list[str] = []
    flagged: list[tuple[str, str, float]] = []

    for entry in entries:
        strategy = entry.strategy_factory()
        session = run_backtest(
            run_id=f"curation:{entry.manifest.id}", symbol=SYMBOL, bars=bars,
            strategy=strategy, starting_cash=Decimal("10000"),
        )
        returns = _bar_returns(session.equity_curve)
        if float(np.std(returns)) == 0.0:
            inert.append(entry.manifest.id)
            continue

        result = correlation_curation_check(
            candidate_id=entry.manifest.id,
            candidate_returns=returns,
            candidate_metric=_sharpe_like(returns),
            existing_returns=returns_by_model,
            existing_metrics=metric_by_model,
        )
        if not result.passed:
            flagged.append(
                (entry.manifest.id, result.most_correlated_to or "?", result.correlation or 0.0)
            )

        # admit it into the "existing" pool regardless of the curation verdict
        # -- this is a report on what *would* have been flagged, not a live
        # gate actually rejecting anything from the real catalog.
        returns_by_model[entry.manifest.id] = returns
        metric_by_model[entry.manifest.id] = _sharpe_like(returns)

    print(f"{len(returns_by_model)} models produced a genuine (non-degenerate) return stream")
    if inert:
        print(f"{len(inert)} models never traded this window, excluded: {', '.join(sorted(inert))}")
    print()
    print("=== Correlation curation report (docs/14 §3) ===")
    if not flagged:
        print("No model would have been flagged as a redundant duplicate driver.")
    else:
        print(f"{len(flagged)} of {len(returns_by_model)} models would have been flagged:")
        for model_id, most_correlated_to, corr in flagged:
            print(f"  {model_id} -- redundant vs {most_correlated_to} (corr={corr:.2f})")
    print()
    print(
        "This is a diagnostic replay against synthetic backtested data, not a live gate -- "
        "every flagged model is still in the real catalog today. See docs/14 §3/HANDOFF.md "
        "for the wiring decision this operationalizes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
