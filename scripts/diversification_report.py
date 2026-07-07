"""docs/14 §1/§7 (v4) M23 exit gate + M24 exit gate, extended docs/15 V5 M28
("Wake the Sleeves"): compute the real diversification score over the full
scaled catalog's actual backtested returns -- not just the sleeve-label
distribution measured in the M23/M24 commits -- and (M24) the carry/basis
sleeve's measured correlation to the directional sleeves.

    python scripts/diversification_report.py

Single-instrument models (the vast majority of the catalog) still run
exactly as before -- one `run_backtest()` call each against `SYMBOL`'s own
book. **V5 M28 fix**: models whose manifest declares a plain-OHLCV,
`instruments > 1` data need (cross-sectional/stat-arb/universe-regime --
the sleeves this milestone wakes; carry_basis's own 2 perp-needing models
also declare `instruments=2` but need a symbol-specific perp leg, not a
`DEFAULT_UNIVERSE` ranking, so they're excluded from this reshaped path by
their distinct `kind="OHLCV+FUNDING"` data need) now run via
`run_universe_backtest`, that model's factory instantiated once per symbol
across the real 5-symbol `DEFAULT_UNIVERSE`, sharing one engine --
previously they were still only ever backtested against `SYMBOL`'s own book
with a synthetic bar stream that didn't even cover their full declared
ranking universe (`DEFAULT_UNIVERSE` includes BNB-USDT/XRP-USDT, which the
old 4-symbol synthetic stream never generated bars for), so they silently
never accumulated enough sibling history to ever fire -- this
diversification measurement had never actually exercised them for real.
Each (model, symbol) pair from that reshaped set is its own diversification
unit, keyed `"{model_id}:{symbol}"` -- consistent with "models x
instruments" now being the real unit the whole V5 universe extension is
about, not just the model alone.

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

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

from lqe.analytics.diversification import (
    DiversificationScore,
    cross_group_average_correlation,
    diversification_score,
)
from lqe.backtest.runner import run_backtest
from lqe.backtest.universe_runner import run_universe_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import DEFAULT_UNIVERSE, build_scaled_catalog
from lqe.models.manifest import ModelManifest

SYMBOL: Symbol = "BTC-USDT"
PERP_SYMBOL: Symbol = "BTC-USDT-PERP"
UNIVERSE = DEFAULT_UNIVERSE
START = datetime(2026, 1, 1, tzinfo=UTC)
N_BARS = 2000
SEED = 42

# docs/15 V5 M29: where the desk's Engine-view diversification panel reads
# this measurement from (a plain disk read, not the engine hot path --
# `lqe desk`/`lqe live`'s own `--diversification` flag default matches this
# path). Shown dated, not live-recomputed -- see ui/data.py's
# `DiversificationPayload` docstring for why.
ARTIFACT_PATH = Path("runs/diversification_score.json")

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
    """A minute-interleaved synthetic stream covering the real 5-symbol
    `DEFAULT_UNIVERSE` (V5 M28 -- previously only BTC/ETH/SOL, which starved
    the cross-sectional/stat-arb models of the BNB-USDT/XRP-USDT history
    their declared ranking universe actually needs) plus a perp leg trading
    at a sustained premium to spot for the basis-carry models. Genuine
    trend, mean-reverting cycles, and cross-symbol structure (BTC drives
    the alts plus idiosyncratic noise) -- deterministic seed, enough regime
    variety for trend/mean-reversion/volatility/cross-sectional/stat-arb/
    universe-regime/carry-basis sleeves to all get a real chance to trade."""
    rng = np.random.default_rng(SEED)
    btc = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n))
    eth = 0.4 * btc + rng.normal(0, 1.0, n) + 40.0
    sol = 0.2 * btc + rng.normal(0, 1.0, n) + 15.0
    bnb = 0.3 * btc + rng.normal(0, 1.2, n) + 25.0
    xrp = 0.1 * btc + rng.normal(0, 0.8, n) + 5.0
    perp = btc * 1.008 + rng.normal(0, 0.3, n)

    series_by_symbol: dict[Symbol, np.ndarray] = {
        "BTC-USDT": btc, "ETH-USDT": eth, "SOL-USDT": sol, "BNB-USDT": bnb, "XRP-USDT": xrp,
        PERP_SYMBOL: perp,
    }
    bars: list[MarketEvent] = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        for symbol, series in series_by_symbol.items():
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


def _write_artifact(score: DiversificationScore, path: Path) -> None:
    """docs/15 V5 M29: writes the exact JSON `ui/data.py::DeskData.diversification()`
    reads. Factored out of `main()` so its serialization can be unit-tested
    without re-running the full (multi-minute) catalog sweep."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "n_bars": N_BARS,
                "universe": list(UNIVERSE),
                "n_models": score.n_models,
                "average_pairwise_correlation": score.average_pairwise_correlation,
                "effective_number_of_bets": score.effective_number_of_bets,
                "n_sleeves": score.n_sleeves,
                "dominant_sleeve": score.dominant_sleeve,
                "max_sleeve_share": score.max_sleeve_share,
            },
            indent=2,
        )
    )


def main() -> int:
    bars = _synthetic_multi_symbol_bars(N_BARS)
    universe_bars = [b for b in bars if b.symbol in UNIVERSE]  # excludes the perp leg

    catalog, _ = build_scaled_catalog(SYMBOL, universe=UNIVERSE)
    entries = catalog.all()
    sleeve_by_model_id = {e.manifest.id: e.manifest.sleeve for e in entries}

    def _is_universe_ranked(entry_manifest: ModelManifest) -> bool:
        # `instruments > 1` alone isn't a precise enough discriminator --
        # carry_basis's 2 perp-needing models also declare `instruments=2`,
        # but they need a symbol-specific perp leg (`kind="OHLCV+FUNDING"`),
        # not a ranking across `DEFAULT_UNIVERSE`. Only the plain-OHLCV,
        # >1-instrument models (cross-sectional/stat-arb/universe-regime)
        # are the ones this milestone wakes across the real universe.
        needs = entry_manifest.data_needs
        return needs.instruments > 1 and needs.kind == "OHLCV"

    single_instrument = [e for e in entries if not _is_universe_ranked(e.manifest)]
    multi_instrument_ids = sorted(
        e.manifest.id for e in entries if _is_universe_ranked(e.manifest)
    )
    print(
        f"running {len(single_instrument)} single-instrument models ({SYMBOL}-scoped) + "
        f"{len(multi_instrument_ids)} cross-instrument models (each run across the real "
        f"{len(UNIVERSE)}-symbol universe) over {N_BARS} synthetic bars..."
    )

    returns_by_model: dict[str, list[float]] = {}
    sleeve_by_model: dict[str, str] = {}
    inert: list[str] = []

    # -- single-instrument models: unchanged from the pre-M28 measurement,
    # one SYMBOL-scoped run_backtest() call each.
    for entry in single_instrument:
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

    # -- cross-instrument models (docs/15 V5 M28): each one is run ONCE
    # across the whole real universe via run_universe_backtest (its factory
    # instantiated once per symbol, sharing one engine) -- (model, symbol)
    # is the real diversification unit for these, not the model alone.
    catalogs_by_symbol = {sym: build_scaled_catalog(sym, universe=UNIVERSE)[0] for sym in UNIVERSE}
    for model_id in multi_instrument_ids:
        try:
            strategies = {
                sym: catalogs_by_symbol[sym].get(model_id).strategy_factory() for sym in UNIVERSE
            }
        except KeyError:
            continue  # shouldn't happen -- every symbol's catalog registers the same ids
        result = run_universe_backtest(
            run_id=f"divscore-universe:{model_id}", symbols=list(UNIVERSE),
            bars=universe_bars, strategies=strategies, starting_cash=Decimal("10000"),
        )
        for sym in UNIVERSE:
            key = f"{model_id}:{sym}"
            returns = _bar_returns(result.sessions[sym].equity_curve)
            if float(np.std(returns)) == 0.0:
                inert.append(key)
                continue
            returns_by_model[key] = returns
            sleeve_by_model[key] = sleeve_by_model_id[model_id]

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

    _write_artifact(score, ARTIFACT_PATH)
    print(f"wrote {ARTIFACT_PATH}")

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
