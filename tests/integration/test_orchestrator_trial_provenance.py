"""Honest cross-campaign trial counting (docs/03 §3.6): when the
orchestrator is given a persistent `ExperimentRegistry`, every trial is
recorded and the count that feeds DSR/PBO is seeded from prior campaigns —
so re-searching the same data can't smuggle a lucky winner past the
deflation. Without a registry the count is purely in-memory (M8 default).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from lqe.analytics.registry import ExperimentRegistry
from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.storage.catalog import Catalog

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(n: int = 220) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 11) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=START + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def _orch(*, run_id: str, registry: ExperimentRegistry | None, n_trials: int = 5) -> Orchestrator:
    return Orchestrator(
        validator=Validator(n_folds=2, random_control_reps=3),
        gate=PromotionGate(thresholds=GateThresholds(min_periods=1, min_trades=1)),
        optimizer=OptunaOptimizer(),
        searchable_models=default_searchable_models(),
        bars=_bars(),
        symbol=SYMBOL,
        starting_cash=Decimal("10000"),
        run_id=run_id,
        seed=1,
        n_trials=n_trials,
        registry=registry,
    )


@pytest.mark.filterwarnings("ignore")
def test_trials_are_persisted_to_the_registry(tmp_path: Path) -> None:
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        registry = ExperimentRegistry(catalog)
        orch = _orch(run_id="campaign-a", registry=registry, n_trials=5)
        orch.run(steps=2, start=START)
        # 2 steps * 5 trials each = 10 rows landed in the trials table
        assert registry.trial_count() == 10
        assert len(registry.trials()) == 10


@pytest.mark.filterwarnings("ignore")
def test_a_second_distinct_campaign_accumulates_the_trial_count(tmp_path: Path) -> None:
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        registry = ExperimentRegistry(catalog)
        _orch(run_id="campaign-a", registry=registry, n_trials=5).run(steps=2, start=START)
        assert registry.trial_count() == 10

        # a different campaign seeds its context from the existing 10 and adds more
        orch_b = _orch(run_id="campaign-b", registry=registry, n_trials=5)
        states = orch_b.run(steps=1, start=START)
        assert registry.trial_count() == 15
        # the honest count fed to the gate spans both campaigns (>= prior 10)
        assert states[0].n_trials_context >= 10


@pytest.mark.filterwarnings("ignore")
def test_an_identical_rerun_does_not_double_count(tmp_path: Path) -> None:
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        registry = ExperimentRegistry(catalog)
        _orch(run_id="campaign-a", registry=registry, n_trials=5).run(steps=2, start=START)
        assert registry.trial_count() == 10
        # same run_id + same trials -> run-scoped PKs REPLACE, no inflation
        _orch(run_id="campaign-a", registry=registry, n_trials=5).run(steps=2, start=START)
        assert registry.trial_count() == 10


@pytest.mark.filterwarnings("ignore")
def test_without_a_registry_counting_is_in_memory_only() -> None:
    orch = _orch(run_id="no-registry", registry=None, n_trials=5)
    states = orch.run(steps=2, start=START)
    assert states[-1].n_trials_context == 10  # purely this run
