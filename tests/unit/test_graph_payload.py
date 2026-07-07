"""The 3D neural-web GraphPayload (docs/11 §11.9, docs/10 M10): built
read-only from the audit, honest node fields, sandbox vs tracked regions,
and deterministic timeline replay via `at_seq`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytest

from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.engine import AuditLog
from lqe.core.events import (
    FillEvent,
    HypothesisEvent,
    MarketEvent,
    Order,
    OrderIntent,
    PromotionEvent,
    RiskStateEvent,
    ValidationEvent,
)
from lqe.core.types import Symbol
from lqe.storage.state_reader import CatalogModelInfo, StateReader

SYMBOL: Symbol = "BTC-USDT"
OTHER_SYMBOL: Symbol = "ETH-USDT"
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


# -- V5 M29 "Universe UI": the real neural-web unit is (model, symbol) ------


def _append_fills(log: AuditLog, seq: int, model: str, symbol: Symbol, n: int) -> int:
    for i in range(n):
        side: Literal["BUY", "SELL"] = "BUY" if i % 2 == 0 else "SELL"
        intent_id = f"i-{model}-{symbol}-{i}"
        order_id = f"order:{intent_id}"
        log.append(
            event_type="OrderIntent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
            payload=OrderIntent(
                intent_id=intent_id, signal_ref=f"s{model}{symbol}{i}", strategy=model,
                symbol=symbol, side=side, qty=Decimal("1"), order_type="MARKET",
                idempotency_key=f"k{model}{symbol}{i}", reason="test",
            ),
        )
        seq += 1
        log.append(
            event_type="Order", run_id="r", seq=seq, book="sandbox", sim_ts=START,
            payload=Order(
                order_id=order_id, intent_ref=intent_id, side=side, qty=Decimal("1"),
                order_type="MARKET", status="PENDING",
            ),
        )
        seq += 1
        log.append(
            event_type="FillEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
            payload=FillEvent(
                order_id=order_id, fill_ts=START, fill_px=Decimal(100 + i),
                fill_qty=Decimal("1"), fee=Decimal("0.01"), slippage_bps=0.5, partial=False,
            ),
        )
        seq += 1
    return seq


def _promotion_log(model: str, symbol: Symbol, *, n_trades: int = 5) -> AuditLog:
    """A model that trades `symbol`, gets explored alongside an untraded
    sibling ("beta"), then validated and promoted."""
    log = AuditLog()
    seq = 1
    log.append(
        event_type="RiskStateEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=RiskStateEvent(
            equity=Decimal("10000"), cash=Decimal("10000"), daily_pnl=Decimal("0"),
            gross_exposure=Decimal("0"), peak_equity=Decimal("10000"), drawdown=0.0,
            open_orders=0, kill_active=False,
        ),
    )
    seq += 1
    # a MarketEvent for `symbol` so `_sole_observed_symbol()` (the tier-2
    # fallback for a model that's explored/promoted but never itself
    # traded, e.g. "beta" below) has something honest to resolve to.
    log.append(
        event_type="MarketEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=MarketEvent(
            exchange="binance", symbol=symbol, timeframe="1m", ts_open=START,
            o=Decimal("100"), h=Decimal("101"), l=Decimal("99"), c=Decimal("100"),
            v=100.0, source_version="test",
        ),
    )
    seq += 1
    seq = _append_fills(log, seq, model, symbol, n_trades)
    log.append(
        event_type="HypothesisEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=HypothesisEvent(
            hypo_id="h1", rationale="test", target_models=[model, "beta"],
            proposed_space={}, regime="test",
        ),
    )
    seq += 1
    candidate_id = f"cand:{model}:0"
    log.append(
        event_type="ValidationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=ValidationEvent(
            candidate_id=candidate_id, result="PASS", dsr=1.5, pbo=0.1,
            cost_survived=True, beats_equal_weight=True, evidence={},
        ),
    )
    seq += 1
    log.append(
        event_type="PromotionEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=PromotionEvent(
            candidate_id=candidate_id, from_book="sandbox", to_book="tracked",
            config_version="v1",
        ),
    )
    return log


def test_promoted_node_resolves_via_its_own_traded_symbol() -> None:
    reader = StateReader(_promotion_log("alpha", SYMBOL).records)
    g = reader.graph()
    tracked = [n for n in g.nodes if n.kind == "tracked"]
    assert len(tracked) == 1
    node = tracked[0]
    assert node.id == f"alpha::{SYMBOL}"
    assert node.symbol == SYMBOL
    assert node.status == "validated"
    assert node.id in g.regions["tracked"]
    # "beta" was explored (HypothesisEvent target) but never traded -- falls
    # back to the reconstruction's own sole observed symbol (the only symbol
    # this audit ever saw a bar/fill for), not a fabricated one.
    beta = next(n for n in g.nodes if n.id.startswith("beta::"))
    assert beta.symbol == SYMBOL


def test_promoted_model_id_with_two_traded_symbols_resolves_to_the_more_active_one() -> None:
    log = AuditLog()
    seq = 1
    log.append(
        event_type="RiskStateEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=RiskStateEvent(
            equity=Decimal("10000"), cash=Decimal("10000"), daily_pnl=Decimal("0"),
            gross_exposure=Decimal("0"), peak_equity=Decimal("10000"), drawdown=0.0,
            open_orders=0, kill_active=False,
        ),
    )
    seq += 1
    seq = _append_fills(log, seq, "alpha", SYMBOL, 3)
    seq = _append_fills(log, seq, "alpha", OTHER_SYMBOL, 8)
    log.append(
        event_type="HypothesisEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=HypothesisEvent(
            hypo_id="h1", rationale="test", target_models=["alpha"],
            proposed_space={}, regime="test",
        ),
    )
    seq += 1
    candidate_id = "cand:alpha:0"
    log.append(
        event_type="ValidationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=ValidationEvent(
            candidate_id=candidate_id, result="PASS", dsr=1.5, pbo=0.1,
            cost_survived=True, beats_equal_weight=True, evidence={},
        ),
    )
    seq += 1
    log.append(
        event_type="PromotionEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=PromotionEvent(
            candidate_id=candidate_id, from_book="sandbox", to_book="tracked",
            config_version="v1",
        ),
    )
    reader = StateReader(log.records)
    g = reader.graph()
    tracked = [n for n in g.nodes if n.kind == "tracked"]
    assert len(tracked) == 1
    # OTHER_SYMBOL had 8 fills vs SYMBOL's 3 -- the more active instance wins
    assert tracked[0].id == f"alpha::{OTHER_SYMBOL}"
    # the promotion doesn't retroactively mark every instance of the same
    # model_id as tracked -- alpha's other (less active) book is still its
    # own, separate, honestly-unpromoted sandbox node.
    other = next(n for n in g.nodes if n.id == f"alpha::{SYMBOL}")
    assert other.kind == "sandbox"


def test_node_cap_never_drops_a_tracked_node_and_collapses_the_rest_into_overflow() -> None:
    catalog = [
        CatalogModelInfo(model_id=f"idle_{i}", family="trend", symbol=SYMBOL) for i in range(200)
    ]
    reader = StateReader(_promotion_log("alpha", SYMBOL).records, catalog=catalog)
    g = reader.graph()
    assert len(g.nodes) <= 150
    tracked = [n for n in g.nodes if n.kind == "tracked"]
    assert len(tracked) == 1 and tracked[0].id == f"alpha::{SYMBOL}"
    overflow = [n for n in g.nodes if n.kind == "overflow"]
    assert overflow, "200 idle catalog models should exceed the node budget"
    for n in overflow:
        # honest zeros -- an overflow marker is a count, never invented state
        assert n.n_trades == 0 and n.sim_return == 0.0 and n.status == "unproven"
        assert n.label.startswith("+") and "idle" in n.label


# -- recent_promotions(): the live feed behind the Promotion Moment ---------


def test_recent_promotions_resolves_symbol_and_pairs_dsr_pbo() -> None:
    log = _promotion_log("alpha", SYMBOL)
    reader = StateReader(log.records)
    rows = reader.recent_promotions()
    assert len(rows) == 1
    row = rows[0]
    assert row.model_id == "alpha"
    assert row.symbol == SYMBOL
    assert row.dsr == pytest.approx(1.5)
    assert row.pbo == pytest.approx(0.1)
    assert row.config_version == "v1"


def test_recent_promotions_after_seq_only_returns_new_ones() -> None:
    log = _promotion_log("alpha", SYMBOL)
    first_promotion_seq = log.records[-1].seq
    # a second, later promotion for a different model on the same log
    seq = first_promotion_seq + 1
    log.append(
        event_type="MarketEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=MarketEvent(
            exchange="binance", symbol=SYMBOL, timeframe="1m", ts_open=START,
            o=Decimal("100"), h=Decimal("101"), l=Decimal("99"), c=Decimal("100"),
            v=100.0, source_version="test",
        ),
    )
    seq += 1
    seq = _append_fills(log, seq, "gamma", SYMBOL, 3)
    log.append(
        event_type="HypothesisEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=HypothesisEvent(
            hypo_id="h2", rationale="test", target_models=["gamma"],
            proposed_space={}, regime="test",
        ),
    )
    seq += 1
    log.append(
        event_type="ValidationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=ValidationEvent(
            candidate_id="cand:gamma:0", result="PASS", dsr=2.0, pbo=0.2,
            cost_survived=True, beats_equal_weight=True, evidence={},
        ),
    )
    seq += 1
    log.append(
        event_type="PromotionEvent", run_id="r", seq=seq, book="sandbox", sim_ts=START,
        payload=PromotionEvent(
            candidate_id="cand:gamma:0", from_book="sandbox", to_book="tracked",
            config_version="v2",
        ),
    )
    reader = StateReader(log.records)
    all_rows = reader.recent_promotions()
    assert [r.model_id for r in all_rows] == ["alpha", "gamma"]
    new_only = reader.recent_promotions(after_seq=first_promotion_seq)
    assert len(new_only) == 1
    assert new_only[0].model_id == "gamma"
    assert new_only[0].symbol == SYMBOL
    assert new_only[0].dsr == pytest.approx(2.0)
    # repeating the same after_seq never re-surfaces an already-seen promotion
    assert reader.recent_promotions(after_seq=new_only[0].seq) == []


def test_recent_promotions_limit_caps_the_most_recent() -> None:
    log = _promotion_log("alpha", SYMBOL)
    reader = StateReader(log.records)
    assert len(reader.recent_promotions(limit=0)) == 1  # 0 means "no cap" here
    assert len(reader.recent_promotions(limit=1)) == 1
