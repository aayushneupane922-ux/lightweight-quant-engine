"""docs/14 §1/§7 (v4) M23 exit gate + M24 exit gate: compute the real
diversification score over the full scaled catalog's actual backtested
returns -- not just the sleeve-label distribution measured in the M23/M24
commits -- and (M24) the carry/basis sleeve's measured correlation to the
directional sleeves.

    python scripts/diversification_report.py

Runs every admitted model in `build_scaled_catalog` against one shared,
synthetic, interleaved 4-symbol bar stream (spot + 2 correlated alts + a
perp leg for the basis-carry models -- via the same multi-symbol `Session`
extension the sleeve C/D/F models need), extracts each model's own per-bar
equity-return series, and feeds them to
`analytics/diversification.py::diversification_score()` and (for M24)
`cross_group_average_correlation()`.

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

from lqe.analytics.diversification import cross_group_average_correlation, diversification_score
from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import build_scaled_catalog

SYMBOL: Symbol = "BTC-USDT"
PERP_SYMBOL: Symbol = "BTC-USDT-PERP"
START = datetime(2026, 1, 1, tzinfo=UTC)
N_BARS = 2000
SEED = 42

# docs/14 M24's exit gate ("measurably low-correlation to directional
# sleeves"): every sleeve whose bet is on an instrument's own price
# direction (trend, reversion, breakout, seasonality, regime, relative-
# value, ML) -- everything except carry_basis itself, the pure allocators
# (which combine sleeves rather than betting on one), and the deliberately-
# weak control.
DIRECTIONAL_SLEEVES = {
    "trend_momentum", "mean_reversion", "volatility", "breakout_structure",
    "seasonality", "regime_overlay", "cross_sectional", "stat_arb", "ml_signal",
}


def _synthetic_multi_symbol_bars(n: int) -> list[MarketEvent]:
    """A 4-symbol, minute-interleaved synthetic stream with genuine trend,
    mean-reverting cycles, cross-symbol structure (BTC drives ETH/SOL plus
    idiosyncratic noise), and a perp leg trading at a sustained premium to
    spot -- deterministic seed, enough regime variety for trend/mean-
    reversion/volatility/cross-sectional/stat-arb/carry-basis sleeves to
    all get a real chance to trade."""
    rng = np.random.default_rng(SEED)
    btc = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n))
    eth = 0.4 * btc + rng.normal(0, 1.0, n) + 40.0
    sol = 0.2 * btc + rng.normal(0, 1.0, n) + 15.0
    perp = btc * 1.008 + rng.normal(0, 0.3, n)

    bars: list[MarketEvent] = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        for symbol, series in (
            ("ETH-USDT", eth), ("SOL-USDT", sol), (PERP_SYMBOL, perp), (SYMBOL, btc),
        ):
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

    if "carry_basis" in sleeve_by_model.values():
        directional_present = DIRECTIONAL_SLEEVES & set(sleeve_by_model.values())
        cross_corr = cross_group_average_correlation(
            returns_by_model, sleeve_by_model, {"carry_basis"}, directional_present,
        )
        print()
        print("=== M24 exit gate: carry_basis vs. directional sleeves ===")
        print(f"directional sleeves compared against: {sorted(directional_present)}")
        print(f"cross_group_average_correlation:      {cross_corr:.4f}")
        print(
            "Target: measurably low vs. the whole-catalog average pairwise correlation above "
            "-- carry/basis signals come from funding/structure, not price direction."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
