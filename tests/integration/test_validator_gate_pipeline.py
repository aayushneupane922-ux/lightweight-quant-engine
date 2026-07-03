"""End-to-end: Validator runs real backtests (walk-forward, cost sweep,
benchmarks) over a synthetic-but-deterministic bar series, and the
PromotionGate turns that evidence into a verdict. Proves the wiring works;
does not assert a specific verdict — that depends on the data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.validator import PromotionCandidate, Validator
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.plugins.trend_ma_cross import TrendMaCross

SYMBOL: Symbol = "BTC-USDT"


def _trending_bars(n: int) -> list[MarketEvent]:
    """A long, gently trending series with small noise-like wobble — long
    enough (and with a real enough drift) for walk-forward folds and the
    cost sweep to have something non-degenerate to chew on."""
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if i % 3 != 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def test_validator_and_gate_pipeline_runs_end_to_end() -> None:
    bars = _trending_bars(400)
    candidate = PromotionCandidate(
        candidate_id="pipeline-test", model_id="trend_ma_cross", params={"fast": 5, "slow": 20},
        book="sandbox", hypo_id="H-1", study_id="S-1", data_version="synthetic", seed=1,
        n_trials_context=10,
    )
    validator = Validator(n_folds=2, random_control_reps=3)
    result = validator.validate(
        candidate, bars=bars, symbol=SYMBOL,
        strategy_factory=lambda: TrendMaCross(symbol=SYMBOL, fast=5, slow=20),
        starting_cash=Decimal("10000"),
    )

    gate = PromotionGate(thresholds=GateThresholds(min_periods=1))  # short synthetic series
    gate_result = gate.check(candidate, result, n_periods=len(bars))

    assert gate_result.verdict in ("PASS", "FAIL")
    assert "fail_reasons" in gate_result.evidence
    assert gate_result.evidence["candidate_id"] == "pipeline-test"
    # the evidence trail is real, not a stub — every benchmark ran
    assert "cost_sweep_sharpe_by_bps" in gate_result.evidence
    assert "buy_hold_sharpe" in gate_result.evidence
    assert "random_control_sharpes" in gate_result.evidence
