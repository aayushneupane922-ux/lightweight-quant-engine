"""docs/14 §1/§7 (v4) M23 exit gate: "score computed" must be a genuine,
repeatable capability, not a one-off script run. This runs the exact same
real pipeline as `scripts/diversification_report.py` (build the scaled
catalog -> real multi-symbol `Session` backtests -> per-bar equity returns
-> `diversification_score()`) end-to-end on a small sample, fast enough for
the default suite. The full 94-model sweep over a longer synthetic window
is `scripts/diversification_report.py` itself (a few minutes; not part of
the default test run, same pattern as `make_demo_run.py`).
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


def _merged_bars(n: int) -> list[MarketEvent]:
    rng = np.random.default_rng(7)
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
                    v=100.0, source_version="test",
                )
            )
    return bars


def _bar_returns(equity_curve: list[Decimal]) -> list[float]:
    return [
        float((cur - prev) / prev) if prev != 0 else 0.0
        for prev, cur in zip(equity_curve, equity_curve[1:])  # noqa: B905 - deliberately uneven
    ]


def test_diversification_score_computes_over_real_backtested_returns() -> None:
    bars = _merged_bars(150)
    catalog, _ = build_scaled_catalog(SYMBOL)
    # a small, sleeve-diverse sample -- not the full 94, but enough to prove
    # the pipeline composes end-to-end across genuinely different sleeves,
    # including the new multi-symbol ones (cross-sectional, stat-arb).
    wanted_ids = {
        "macd_trend_0", "zscore_reversion_0", "vol_breakout_0",
        "xsec_momentum", "stat_arb_distance_0", "trend_ma_cross_5_20",
    }
    sample = [e for e in catalog.all() if e.manifest.id in wanted_ids]
    assert len(sample) == len(wanted_ids)  # every id must actually resolve

    returns_by_model: dict[str, list[float]] = {}
    sleeve_by_model: dict[str, str] = {}
    for entry in sample:
        strategy = entry.strategy_factory()
        session = run_backtest(
            run_id=f"divscore-test:{entry.manifest.id}", symbol=SYMBOL, bars=bars,
            strategy=strategy, starting_cash=Decimal("10000"),
        )
        returns = _bar_returns(session.equity_curve)
        if float(np.std(returns)) == 0.0:
            continue  # never traded this window -- correlation undefined, honestly excluded
        returns_by_model[entry.manifest.id] = returns
        sleeve_by_model[entry.manifest.id] = entry.manifest.sleeve

    assert len(returns_by_model) >= 2

    score = diversification_score(returns_by_model, sleeve_by_model)
    assert score.n_models == len(returns_by_model)
    assert -1.0 <= score.average_pairwise_correlation <= 1.0
    assert 1.0 <= score.effective_number_of_bets <= score.n_models
    assert score.n_sleeves >= 2
    assert 0.0 < score.max_sleeve_share <= 1.0
