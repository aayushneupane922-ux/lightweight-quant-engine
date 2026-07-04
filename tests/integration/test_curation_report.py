"""docs/14 §3 (v4): "wire correlation curation into a pipeline" must be a
genuine, repeatable capability, not a one-off script run. This proves the
same real building blocks `scripts/curation_report.py` sweeps across the
full 104-model catalog -- real `Session` backtests -> real per-bar equity
returns -> `correlation_curation_check` -- correctly flag a genuine
duplicate driver, fast enough for the default suite (the full catalog
sweep takes a few minutes and stays a standalone script, same pattern as
`scripts/diversification_report.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from lqe.backtest.runner import run_backtest
from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.catalog_scale import build_scaled_catalog
from lqe.models.curation import correlation_curation_check

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(n: int) -> list:
    from lqe.core.events import MarketEvent

    rng = np.random.default_rng(7)
    btc = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n))
    bars = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        price = Decimal(str(round(float(btc[i]), 4)))
        bars.append(
            MarketEvent(
                exchange="synthetic", symbol=SYMBOL, timeframe="1m", ts_open=ts,
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


def _sharpe_like(returns: list[float]) -> float:
    std = float(np.std(returns))
    return float(np.mean(returns)) / std if std > 0 else 0.0


def test_correlation_curation_flags_a_genuine_duplicate_over_real_backtested_returns() -> None:
    bars = _bars(150)
    # two identically-parameterized MACD strategies -- a real duplicate
    # driver by construction (correlation ~1.0, near-identical metric), the
    # textbook case docs/14 §3 exists to catch. Real `run_backtest` Session
    # runs, not synthetic hand-crafted return arrays.
    params = {"fast": 12.0, "slow": 26.0, "signal": 9.0}
    original = run_backtest(
        run_id="curation-test:original", symbol=SYMBOL, bars=bars,
        strategy=IndicatorRuleAdapter(symbol=SYMBOL, preset="macd_trend", name="a", params=params),
        starting_cash=Decimal("10000"),
    )
    duplicate = run_backtest(
        run_id="curation-test:duplicate", symbol=SYMBOL, bars=bars,
        strategy=IndicatorRuleAdapter(symbol=SYMBOL, preset="macd_trend", name="b", params=params),
        starting_cash=Decimal("10000"),
    )
    original_returns = _bar_returns(original.equity_curve)
    duplicate_returns = _bar_returns(duplicate.equity_curve)
    assert float(np.std(original_returns)) > 0.0  # a real, non-degenerate trade happened

    first = correlation_curation_check(
        candidate_id="original", candidate_returns=original_returns,
        candidate_metric=_sharpe_like(original_returns),
        existing_returns={}, existing_metrics={},
    )
    assert first.passed  # nothing to be redundant with yet

    second = correlation_curation_check(
        candidate_id="duplicate", candidate_returns=duplicate_returns,
        candidate_metric=_sharpe_like(duplicate_returns),
        existing_returns={"original": original_returns},
        existing_metrics={"original": _sharpe_like(original_returns)},
    )
    assert not second.passed
    assert second.most_correlated_to == "original"
    assert second.correlation == 1.0


def test_curation_report_pipeline_resolves_against_the_real_scaled_catalog() -> None:
    # a lighter integration check that the real scaled-catalog path (which
    # `scripts/curation_report.py` walks in full) at least resolves model
    # ids and runs real backtests without error -- the full 104-model sweep
    # itself lives in the standalone script, not the default test suite.
    bars = _bars(150)
    catalog, _ = build_scaled_catalog(SYMBOL)
    entry = next(e for e in catalog.all() if e.manifest.id == "macd_trend_0")
    session = run_backtest(
        run_id="curation-test:catalog", symbol=SYMBOL, bars=bars,
        strategy=entry.strategy_factory(), starting_cash=Decimal("10000"),
    )
    returns = _bar_returns(session.equity_curve)
    result = correlation_curation_check(
        candidate_id=entry.manifest.id, candidate_returns=returns,
        candidate_metric=_sharpe_like(returns), existing_returns={}, existing_metrics={},
    )
    assert result.passed
