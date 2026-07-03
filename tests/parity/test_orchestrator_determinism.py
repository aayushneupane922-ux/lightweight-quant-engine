"""The autonomy loop is deterministic and replays from its log (docs/11
§11.8, docs/10 M8 exit gate): same seed+inputs → identical audit hash
chain, and a persisted log reloads and re-verifies to the same head.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.engine import AuditLog
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol

SYMBOL: Symbol = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(n: int = 260) -> list[MarketEvent]:
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


def _orch() -> Orchestrator:
    return Orchestrator(
        validator=Validator(n_folds=2, random_control_reps=3),
        gate=PromotionGate(thresholds=GateThresholds(min_periods=1, min_trades=1)),
        optimizer=OptunaOptimizer(),
        searchable_models=default_searchable_models(),
        bars=_bars(),
        symbol=SYMBOL,
        starting_cash=Decimal("10000"),
        seed=3,
        n_trials=5,
    )


@pytest.mark.filterwarnings("ignore")
def test_two_runs_same_seed_produce_identical_audit_chains() -> None:
    a = _orch()
    a.run(steps=3, start=START)
    b = _orch()
    b.run(steps=3, start=START)
    assert a.engine.audit.head_hash == b.engine.audit.head_hash
    assert [e.hash for e in a.engine.audit.records] == [e.hash for e in b.engine.audit.records]


@pytest.mark.filterwarnings("ignore")
def test_audit_log_persists_and_replays_from_disk(tmp_path: Path) -> None:
    orch = _orch()
    orch.run(steps=2, start=START)
    path = tmp_path / "autopilot-audit.jsonl"
    orch.engine.audit.write_jsonl(path)

    reloaded = AuditLog.from_jsonl(path)  # re-verifies the chain on load
    assert reloaded.verify()
    assert reloaded.head_hash == orch.engine.audit.head_hash
