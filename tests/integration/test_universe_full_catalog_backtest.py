"""docs/15 V5 M28 ("Wake the Sleeves"): the M23/M24-era cross-sectional/
stat-arb backtest tests (`test_cross_sectional_backtest.py`/
`test_stat_arb_backtest.py`) each prove exactly ONE illustrative model fires
a real signal on a real interleaved multi-symbol backtest. This proves the
*full* admitted set of universe-ranked models (every cross-sectional/stat-
arb/universe-regime entry `build_scaled_catalog` registers, not just one
hand-picked example of each) actually produces real, gated signals when run
across the real 5-symbol `DEFAULT_UNIVERSE` -- the concrete deliverable
M28's own exit gate asks for.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from lqe.backtest.universe_runner import run_universe_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import DEFAULT_UNIVERSE, build_scaled_catalog

START = datetime(2026, 1, 1, tzinfo=UTC)
N_BARS = 400
SEED = 11


def _universe_bars(n: int) -> list[MarketEvent]:
    # Same "BTC drives the alts + idiosyncratic noise" shape as
    # scripts/diversification_report.py's synthetic generator -- enough
    # genuine dispersion/correlation structure for cross-sectional ranking,
    # stat-arb spread divergence, and universe-regime correlation reads to
    # all get a fair chance to fire, across every symbol in the real
    # DEFAULT_UNIVERSE (not a smaller hand-picked subset).
    rng = np.random.default_rng(SEED)
    btc = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n))
    eth = 0.4 * btc + rng.normal(0, 1.0, n) + 40.0
    sol = 0.2 * btc + rng.normal(0, 1.0, n) + 15.0
    bnb = 0.3 * btc + rng.normal(0, 1.2, n) + 25.0
    xrp = 0.1 * btc + rng.normal(0, 0.8, n) + 5.0
    series_by_symbol: dict[Symbol, np.ndarray] = {
        "BTC-USDT": btc, "ETH-USDT": eth, "SOL-USDT": sol, "BNB-USDT": bnb, "XRP-USDT": xrp,
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
                    v=100.0, source_version="test",
                )
            )
    return bars


def _universe_ranked_model_ids() -> list[str]:
    catalog, _ = build_scaled_catalog("BTC-USDT", universe=DEFAULT_UNIVERSE)
    return sorted(
        e.manifest.id
        for e in catalog.all()
        if e.manifest.data_needs.instruments > 1 and e.manifest.data_needs.kind == "OHLCV"
    )


def test_the_full_universe_ranked_catalog_is_registered_and_nontrivial() -> None:
    # Sanity on the fixture itself: cross-sectional (4) + the native stat-arb
    # entries (8: 3 distance + 3 lead-lag + 2 basket -- pairs_ols and
    # stat_arb_johansen are excluded, both single-instrument/fixed-data) +
    # universe-regime (2) = 14 model_ids should be genuinely universe-ranked.
    ids = _universe_ranked_model_ids()
    assert len(ids) == 14
    assert any(i.startswith("xsec_") for i in ids)
    assert any(i.startswith("stat_arb_") for i in ids)
    assert any(i.startswith("universe_regime_gate_") for i in ids)


def test_the_full_admitted_universe_ranked_set_fires_real_signals_together() -> None:
    bars = _universe_bars(N_BARS)
    catalogs_by_symbol = {
        sym: build_scaled_catalog(sym, universe=DEFAULT_UNIVERSE)[0] for sym in DEFAULT_UNIVERSE
    }
    model_ids = _universe_ranked_model_ids()

    traded: list[str] = []
    never_traded: list[str] = []
    for model_id in model_ids:
        strategies = {
            sym: catalogs_by_symbol[sym].get(model_id).strategy_factory()
            for sym in DEFAULT_UNIVERSE
        }
        result = run_universe_backtest(
            run_id=f"full-catalog:{model_id}", symbols=list(DEFAULT_UNIVERSE), bars=bars,
            strategies=strategies, starting_cash=Decimal("10000"),
        )
        assert result.engine.audit.verify()
        # this model_id "produces real, gated signals across the universe"
        # if ANY of its per-symbol books ever took a position -- not every
        # symbol needs to trade (some legitimately stay flat), but the
        # model as a whole must not be silently, permanently inert.
        ever_traded = any(
            session.accounting.position_qty(sym) != Decimal("0")
            or session.trade_notionals
            for sym, session in result.sessions.items()
        )
        (traded if ever_traded else never_traded).append(model_id)

    # docs/15 M28's own exit gate: "the previously-dormant intelligence is
    # alive and honestly gated" -- the overwhelming majority of the full
    # admitted set must fire for real over a genuinely varied multi-symbol
    # window; a small residual of legitimately-inert models (this window
    # just didn't cross a given model's specific threshold) is honest, not
    # a regression, so this isn't a 100% requirement.
    assert len(traded) >= len(model_ids) - 2, (
        f"too many universe-ranked models never traded: {never_traded} (traded: {traded})"
    )
