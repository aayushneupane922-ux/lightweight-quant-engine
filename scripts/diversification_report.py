"""docs/14 §1/§7 (v4) M23 exit gate: compute the real diversification score
over the full scaled catalog's actual backtested returns -- not just the
sleeve-label distribution already measured in the M23 commits.

    python scripts/diversification_report.py

Runs every admitted model in `build_scaled_catalog` against one shared,
synthetic, interleaved 3-symbol bar stream (via the same multi-symbol
`Session` extension the sleeve C/D models need), extracts each model's own
per-bar equity-return series, and feeds them to
`analytics/diversification.py::diversification_score()`.

Honesty notes (this is a diagnostic measurement, not a promotion claim,
per non-negotiable #9):
- This runs on synthetic backtested data, not real out-of-sample market
  data -- it measures the *shape* of the catalog's return-driver mix, not
  live edge.
- No model in this project has been promoted to the tracked book yet (the
  demo bundle's trade/period counts are too small to clear the gate,
  per HANDOFF.md); docs/14 §7's "tracked/promoted set" criterion has no
  populated set to measure yet. This script instead reports the full
  *unproven* catalog, which is what M23's own milestone text ("score
  computed") actually asks for at this stage -- re-run this same function
  against the tracked set once real promotion exists.
- A model that never traded across this window has a zero-variance return
  stream, for which correlation is undefined; those are excluded from the
  score and reported separately, not silently dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from lqe.analytics.diversification import diversification_score
from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import build_scaled_catalog

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)
N_BARS = 2000
SEED = 42


def _synthetic_multi_symbol_bars(n: int) -> list[MarketEvent]:
    """A 3-symbol, minute-interleaved synthetic stream with genuine trend,
    mean-reverting cycles, and cross-symbol structure (BTC drives ETH/SOL
    plus idiosyncratic noise) -- deterministic seed, enough regime variety
    for trend/mean-reversion/volatility/cross-sectional/stat-arb sleeves to
    all get a real chance to trade."""
    rng = np.random.default_rng(SEED)
    btc = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n))
    eth = 0.4 * btc + rng.normal(0, 1.0, n) + 40.0
    sol = 0.2 * btc + rng.normal(0, 1.0, n) + 15.0

    bars: list[MarketEvent] = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        for symbol, series in (("ETH-USDT", eth), ("SOL-USDT", sol), (SYMBOL, btc)):
            price = Decimal(str(round(float(series[i]), 4)))
            bars.append(
                MarketEvent(
                    exchange="synthetic", symbol=symbol, timeframe="1m", ts_open=ts,
                    o=price, h=price + Decimal("0.5"), l=price - Decimal("0.5"), c=price,
                    v=100.0, source_version="diversification-report",
                )
            )
    return bars


def _bar_returns(equity_curve: list[Decimal]) -> list[float]:
    returns = []
    for prev, cur in zip(equity_curve, equity_curve[1:]):  # noqa: B905 - deliberately uneven
        returns.append(float((cur - prev) / prev) if prev != 0 else 0.0)
    return returns


def main() -> int:
    bars = _synthetic_multi_symbol_bars(N_BARS)
    catalog, _ = build_scaled_catalog(SYMBOL)
    entries = catalog.all()
    print(f"running {len(entries)} admitted models over {N_BARS} synthetic multi-symbol bars...")

    returns_by_model: dict[str, list[float]] = {}
    sleeve_by_model: dict[str, str] = {}
    inert: list[str] = []
    for entry in entries:
        strategy = entry.strategy_factory()
        session = run_backtest(
            run_id=f"divscore:{entry.manifest.id}", symbol=SYMBOL, bars=bars,
            strategy=strategy, starting_cash=Decimal("10000"),
        )
        returns = _bar_returns(session.equity_curve)
        if float(np.std(returns)) == 0.0:
            inert.append(entry.manifest.id)
            continue
        returns_by_model[entry.manifest.id] = returns
        sleeve_by_model[entry.manifest.id] = entry.manifest.sleeve

    print(f"{len(returns_by_model)} models produced a genuine (non-degenerate) return stream")
    if inert:
        print(
            f"{len(inert)} models never traded over this window (zero-variance returns, "
            f"excluded from correlation): {', '.join(sorted(inert))}"
        )

    score = diversification_score(returns_by_model, sleeve_by_model)
    print()
    print("=== Diversification score (docs/14 §1/§7) ===")
    print(f"n_models (non-degenerate):     {score.n_models}")
    print(f"average_pairwise_correlation:  {score.average_pairwise_correlation:.4f}")
    print(f"effective_number_of_bets:      {score.effective_number_of_bets:.2f}")
    print(f"n_sleeves:                     {score.n_sleeves}")
    print(f"dominant_sleeve:               {score.dominant_sleeve}")
    print(f"max_sleeve_share:              {score.max_sleeve_share:.1%}")
    print()
    print("docs/14 §7 targets: >=8-10 sleeves, avg corr < ~0.3, no sleeve dominating.")
    print(
        "This is the full unproven catalog on synthetic backtested data -- a diagnostic "
        "measurement, not a claim about the (currently empty) tracked/promoted book."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
