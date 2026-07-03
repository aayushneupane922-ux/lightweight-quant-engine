from decimal import Decimal

import numpy as np

from lqe.analytics.metrics import (
    cagr,
    compute_metrics,
    hit_rate,
    max_drawdown,
    payoff_ratio,
    returns_from_equity,
    sharpe_ratio,
)


def test_returns_from_equity_basic() -> None:
    equity = [Decimal("100"), Decimal("110"), Decimal("99")]
    returns = returns_from_equity(equity)
    assert abs(returns[0] - 0.10) < 1e-9
    assert abs(returns[1] - (-0.1)) < 1e-9


def test_sharpe_ratio_zero_for_constant_returns() -> None:
    # zero variance -> defined as 0.0, not NaN/inf
    returns = np.array([0.01, 0.01, 0.01])
    assert sharpe_ratio(returns, periods_per_year=252) == 0.0


def test_sharpe_ratio_positive_for_a_positive_drift() -> None:
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.001, scale=0.005, size=200)
    assert sharpe_ratio(returns, periods_per_year=252) > 0


def test_max_drawdown_detects_the_correct_trough() -> None:
    equity = [Decimal(v) for v in ["100", "120", "90", "95", "130"]]
    dd, duration = max_drawdown(equity)
    assert abs(dd - (120 - 90) / 120) < 1e-9
    assert duration == 2  # two consecutive bars underwater before recovery


def test_cagr_doubling_in_one_year() -> None:
    equity = [Decimal("100"), Decimal("200")]
    value = cagr(equity, periods_per_year=1)
    assert abs(value - 1.0) < 1e-9


def test_hit_rate_and_payoff_ratio() -> None:
    pnls = [10.0, -5.0, 20.0, -10.0]
    assert hit_rate(pnls) == 0.5
    assert abs(payoff_ratio(pnls) - (15.0 / 7.5)) < 1e-9


def test_compute_metrics_end_to_end_shapes() -> None:
    equity = [Decimal(100 + i) for i in range(50)]
    metrics = compute_metrics(
        equity_curve=equity,
        trade_pnls=[5.0, -2.0, 3.0],
        trade_notionals=[Decimal("1000"), Decimal("500")],
        periods_per_year=365 * 24 * 60,
    )
    assert metrics.n_periods == 50
    assert metrics.n_trades == 3
    assert metrics.turnover > 0
