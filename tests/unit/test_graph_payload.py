"""The 3D neural-web GraphPayload (docs/11 §11.9, docs/10 M10): built
read-only from the audit, honest node fields, sandbox vs tracked regions,
and deterministic timeline replay via `at_seq`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.storage.state_reader import StateReader

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


def _reader() -> StateReader:
    lenient = GateThresholds(min_periods=1, min_trades=1, min_dsr=0.0, max_pbo=1.0)
    orch = Orchestrator(
        validator=Validator(n_folds=2, random_control_reps=3),
        gate=PromotionGate(thresholds=lenient),
        optimizer=OptunaOptimizer(), searchable_models=default_searchable_models(),
        bars=_bars(), symbol=SYMBOL, starting_cash=Decimal("10000"), seed=1, n_trials=4,
    )
    orch.run(steps=3, start=START)
    return StateReader(orch.engine.audit.records)


@pytest.fixture(scope="module")
def graph_reader() -> StateReader:
    return _reader()


def test_graph_always_marks_simulated(graph_reader: StateReader) -> None:
    assert graph_reader.graph().simulated is True


def test_graph_has_model_feed_and_meta_nodes(graph_reader: StateReader) -> None:
    g = graph_reader.graph()
    kinds = {n.kind for n in g.nodes}
    assert "meta" in kinds and "regime" in kinds  # meta-layer + feed
    model_nodes = [n for n in g.nodes if n.kind in ("tracked", "sandbox")]
    assert model_nodes, "expected model nodes derived from the autonomy events"
    # honesty fields present on every model node
    for n in model_nodes:
        assert n.n_trades >= 0
        assert n.status in ("unproven", "validated")


def test_promoted_model_is_tracked_and_validated(graph_reader: StateReader) -> None:
    g = graph_reader.graph()
    tracked = [n for n in g.nodes if n.kind == "tracked"]
    assert tracked, "expected at least one promoted -> tracked model"
    for n in tracked:
        assert n.status == "validated"
        assert n.id in g.regions["tracked"]
    # regions never overlap
    assert not (set(g.regions["tracked"]) & set(g.regions["sandbox"]))


def test_edges_are_only_honestly_derivable_kinds(graph_reader: StateReader) -> None:
    g = graph_reader.graph()
    kinds = {link.kind for link in g.links}
    assert kinds <= {"dataflow", "attention", "promotion"}  # no faked corr edges
    # a promotion edge exists for the promoted model
    assert any(link.kind == "promotion" for link in g.links)


def test_replay_at_seq_is_monotonic_and_deterministic(graph_reader: StateReader) -> None:
    full = graph_reader.graph()
    early = graph_reader.graph(at_seq=5)
    assert early.at_seq == 5
    assert len(early.nodes) <= len(full.nodes)
    assert len(early.regions["tracked"]) <= len(full.regions["tracked"])
    # deterministic: same seq -> byte-identical payload
    assert graph_reader.graph(at_seq=5).model_dump() == early.model_dump()


def test_empty_audit_yields_an_empty_but_valid_graph() -> None:
    g = StateReader([]).graph()
    assert g.simulated is True
    assert g.nodes == [] and g.links == []
    assert g.regions == {"tracked": [], "sandbox": []}
