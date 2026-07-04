"""`StateReader` reconstructs UI state read-only from an audit log
(docs/11 §11.9): honesty fields always present, per-model state/return/
sample size derived by replaying events, structured tape rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.runner import run_backtest
from lqe.core.engine import AuditLog
from lqe.core.events import (
    ControlEvent,
    DeRiskEvent,
    FillEvent,
    HypothesisEvent,
    MarketEvent,
    NarrationEvent,
    Order,
    OrderIntent,
    PromotionEvent,
    RiskDecision,
    RiskStateEvent,
    TrialEvent,
    ValidationEvent,
)
from lqe.core.types import Symbol
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.storage.state_reader import CatalogModelInfo, StateReader, blotter_empty_state_reason

SYMBOL: Symbol = "BTC-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(n: int) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 10) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def _reader() -> StateReader:
    session = run_backtest(
        run_id="sr-test", symbol=SYMBOL, bars=_bars(120),
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    return StateReader(
        session.engine.audit.records,
        catalog=[CatalogModelInfo(model_id="trend_ma_cross", family="trend", status="unproven")],
    )


def test_snapshot_always_reports_simulated_true() -> None:
    snap = _reader().snapshot()
    assert snap.simulated is True


def test_snapshot_carries_session_stats_from_the_last_risk_state() -> None:
    snap = _reader().snapshot()
    assert snap.session is not None
    assert snap.session.equity > 0
    assert snap.session.drawdown >= 0.0


def test_model_cell_carries_sample_size_and_status() -> None:
    snap = _reader().snapshot()
    cell = next(c for c in snap.models if c.model_id == "trend_ma_cross")
    assert cell.family == "trend"
    assert cell.status == "unproven"  # never "validated" without a gate PASS
    assert cell.n_trades > 0
    assert cell.sim_return_pct is not None


def test_a_catalog_model_that_never_traded_shows_no_return_and_zero_trades() -> None:
    session = run_backtest(
        run_id="sr-empty", symbol=SYMBOL, bars=_bars(120),
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    reader = StateReader(
        session.engine.audit.records,
        catalog=[
            CatalogModelInfo(model_id="trend_ma_cross", family="trend"),
            CatalogModelInfo(model_id="never_ran", family="momentum"),
        ],
    )
    snap = reader.snapshot()
    idle = next(c for c in snap.models if c.model_id == "never_ran")
    assert idle.n_trades == 0
    assert idle.sim_return_pct is None  # rendered "—", not a fake 0.0
    assert idle.state == "ARMED"
    # V5 M26 living cells: a model that never traded has an empty sparkline
    # and a flat (0%) stance -- never a fake/default-looking value.
    assert idle.sparkline_pct == []
    assert idle.stance_pct == 0.0


def _fills_log(n_fills: int) -> AuditLog:
    """A single strategy ("alpha") alternating BUY/SELL fills of 1 unit
    each -- every fill is a round trip against the previous one, so every
    fill (buy or sell) produces a `sim_return_pct` sample. Used to exercise
    the sparkline's 24-sample cap without depending on organic backtest
    trade counts."""
    log = AuditLog()
    seq = 1
    log.append(
        event_type="RiskStateEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=RiskStateEvent(
            equity=Decimal("10000"), cash=Decimal("10000"), daily_pnl=Decimal("0"),
            gross_exposure=Decimal("0"), peak_equity=Decimal("10000"), drawdown=0.0,
            open_orders=0, kill_active=False,
        ),
    )
    seq += 1
    for i in range(n_fills):
        side = "BUY" if i % 2 == 0 else "SELL"
        intent_id = f"i-{i}"
        order_id = f"order:{intent_id}"
        log.append(
            event_type="OrderIntent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=OrderIntent(
                intent_id=intent_id, signal_ref=f"s{i}", strategy="alpha", symbol=SYMBOL,
                side=side, qty=Decimal("1"), order_type="MARKET",
                idempotency_key=f"k{i}", reason="test",
            ),
        )
        seq += 1
        log.append(
            event_type="Order", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=Order(
                order_id=order_id, intent_ref=intent_id, side=side, qty=Decimal("1"),
                order_type="MARKET", status="PENDING",
            ),
        )
        seq += 1
        log.append(
            event_type="FillEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=FillEvent(
                order_id=order_id, fill_ts=NOW, fill_px=Decimal(100 + i),
                fill_qty=Decimal("1"), fee=Decimal("0.01"), slippage_bps=0.5, partial=False,
            ),
        )
        seq += 1
    return log


def test_sparkline_caps_at_24_samples_regardless_of_fill_count() -> None:
    reader = StateReader(_fills_log(30).records)
    cell = next(c for c in reader.snapshot().models if c.model_id == "alpha")
    assert len(cell.sparkline_pct) == 24
    assert all(isinstance(x, float) for x in cell.sparkline_pct)


def test_sparkline_shorter_than_cap_keeps_every_sample() -> None:
    reader = StateReader(_fills_log(5).records)
    cell = next(c for c in reader.snapshot().models if c.model_id == "alpha")
    assert len(cell.sparkline_pct) == 5


def test_stance_pct_is_bounded_and_reflects_the_open_position() -> None:
    # 30 fills alternating BUY/SELL from a flat start ends net long 1 unit
    # (BUY, SELL, BUY, SELL, ... BUY -- 15 buys, 15 sells... actually 30 is
    # even, so it ends flat; use an odd count to end holding a position).
    reader = StateReader(_fills_log(29).records)
    cell = next(c for c in reader.snapshot().models if c.model_id == "alpha")
    assert 0.0 <= cell.stance_pct <= 1.0
    assert cell.stance_pct > 0.0  # holds an open long position


def test_stance_and_sparkline_are_deterministic_on_replay() -> None:
    records = _fills_log(29).records
    a = StateReader(records).snapshot()
    b = StateReader(records).snapshot()
    cell_a = next(c for c in a.models if c.model_id == "alpha")
    cell_b = next(c for c in b.models if c.model_id == "alpha")
    assert cell_a.sparkline_pct == cell_b.sparkline_pct
    assert cell_a.stance_pct == cell_b.stance_pct


def test_tape_is_incremental_and_capped() -> None:
    reader = _reader()
    everything = reader.tape(after_seq=0, limit=100000)
    assert everything, "expected a non-empty tape"
    highest = everything[-1].seq
    # nothing strictly after the last seq
    assert reader.tape(after_seq=highest) == []
    # the limit keeps only the most-recent rows
    assert len(reader.tape(after_seq=0, limit=3)) == 3


def test_data_health_reports_bars_seen_per_symbol() -> None:
    snap = _reader().snapshot()
    health = next(h for h in snap.data_health if h.symbol == SYMBOL)
    assert health.bars_seen == 120
    assert health.last_bar is not None


# -- charts (docs/13 M19) --------------------------------------------------


def test_price_series_returns_ohlcv_bars_for_the_symbol_oldest_first() -> None:
    bars = _reader().price_series(SYMBOL)
    assert len(bars) == 120
    assert bars == sorted(bars, key=lambda b: b.ts)
    assert all(b.h >= b.o and b.h >= b.c and b.l <= b.o and b.l <= b.c for b in bars)


def test_price_series_is_empty_for_an_unknown_symbol() -> None:
    assert _reader().price_series("ETH-USDT") == []


def test_equity_curve_returns_one_point_per_risk_state_event_oldest_first() -> None:
    points = _reader().equity_curve()
    assert points, "expected a non-empty equity curve"
    assert points == sorted(points, key=lambda p: p.ts)


def test_charts_downsample_to_max_points_preserving_first_and_last() -> None:
    reader = StateReader(
        run_backtest(
            run_id="sr-downsample", symbol=SYMBOL, bars=_bars(500),
            strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
        ).engine.audit.records,
        catalog=[CatalogModelInfo(model_id="trend_ma_cross", family="trend")],
    )
    full = reader.price_series(SYMBOL, max_points=100_000)
    downsampled = reader.price_series(SYMBOL, max_points=50)
    assert len(full) > 50
    assert len(downsampled) <= 50
    assert downsampled[0].ts == full[0].ts
    assert downsampled[-1].ts == full[-1].ts


def test_charts_are_a_noop_when_already_within_budget() -> None:
    reader = _reader()
    assert reader.price_series(SYMBOL, max_points=1000) == reader.price_series(
        SYMBOL, max_points=100_000
    )


# -- blotter (docs/13 M20) --------------------------------------------------


def _blotter_log() -> AuditLog:
    """A hand-built audit log covering all three risk verdicts: a REJECTed
    intent (no Order/Fill at all), a CLAMPed intent that still gets a
    partial then a final fill, and a plain APPROVEd intent with one fill."""
    log = AuditLog()
    seq = 1

    # 1) REJECT -- duplicate_signal, say -- never becomes an Order.
    rejected_intent = OrderIntent(
        intent_id="i-reject", signal_ref="s1", strategy="alpha", symbol=SYMBOL, side="BUY",
        qty=Decimal("5"), order_type="MARKET", idempotency_key="k1", reason="fast > slow",
    )
    log.append(
        event_type="OrderIntent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=rejected_intent,
    )
    seq += 1
    log.append(
        event_type="RiskDecision", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=RiskDecision(
            intent_ref="i-reject", verdict="REJECT", approved_qty=Decimal("0"),
            rule_hits=["duplicate_signal"], detail={},
        ),
    )
    seq += 1

    # 2) CLAMP -- approved less than requested -- becomes an Order, gets a
    #    partial fill then a final fill (two blotter rows, one intent).
    clamped_intent = OrderIntent(
        intent_id="i-clamp", signal_ref="s2", strategy="beta", symbol=SYMBOL, side="SELL",
        qty=Decimal("10"), order_type="MARKET", idempotency_key="k2", reason="slow > fast",
    )
    log.append(
        event_type="OrderIntent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=clamped_intent,
    )
    seq += 1
    log.append(
        event_type="RiskDecision", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=RiskDecision(
            intent_ref="i-clamp", verdict="CLAMP", approved_qty=Decimal("6"),
            rule_hits=["max_position"], detail={},
        ),
    )
    seq += 1
    log.append(
        event_type="Order", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=Order(
            order_id="order:i-clamp", intent_ref="i-clamp", side="SELL", qty=Decimal("6"),
            order_type="MARKET", status="PENDING",
        ),
    )
    seq += 1
    log.append(
        event_type="FillEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=FillEvent(
            order_id="order:i-clamp", fill_ts=NOW, fill_px=Decimal("100"), fill_qty=Decimal("4"),
            fee=Decimal("0.1"), slippage_bps=1.0, partial=True,
        ),
    )
    seq += 1
    log.append(
        event_type="FillEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=FillEvent(
            order_id="order:i-clamp", fill_ts=NOW, fill_px=Decimal("101"), fill_qty=Decimal("2"),
            fee=Decimal("0.05"), slippage_bps=1.5, partial=False,
        ),
    )
    seq += 1

    # 3) APPROVE -- plain, one fill.
    approved_intent = OrderIntent(
        intent_id="i-approve", signal_ref="s3", strategy="alpha", symbol=SYMBOL, side="BUY",
        qty=Decimal("3"), order_type="MARKET", idempotency_key="k3", reason="fast > slow again",
    )
    log.append(
        event_type="OrderIntent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=approved_intent,
    )
    seq += 1
    log.append(
        event_type="RiskDecision", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=RiskDecision(
            intent_ref="i-approve", verdict="APPROVE", approved_qty=Decimal("3"),
            rule_hits=[], detail={},
        ),
    )
    seq += 1
    log.append(
        event_type="Order", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=Order(
            order_id="order:i-approve", intent_ref="i-approve", side="BUY", qty=Decimal("3"),
            order_type="MARKET", status="PENDING",
        ),
    )
    seq += 1
    log.append(
        event_type="FillEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=FillEvent(
            order_id="order:i-approve", fill_ts=NOW, fill_px=Decimal("99"), fill_qty=Decimal("3"),
            fee=Decimal("0.05"), slippage_bps=0.5, partial=False,
        ),
    )
    return log


def test_blotter_gives_a_rejected_intent_exactly_one_no_fill_row() -> None:
    rows = StateReader(_blotter_log().records).blotter()
    rejected = [r for r in rows if r.model == "alpha" and r.verdict == "REJECT"]
    assert len(rejected) == 1
    r = rejected[0]
    assert r.fill_qty is None and r.fill_px is None and r.sim_pnl is None
    assert r.rule_hits == ["duplicate_signal"]
    assert r.intent_qty == Decimal("5")


def test_blotter_gives_a_clamped_intent_one_row_per_fill() -> None:
    rows = StateReader(_blotter_log().records).blotter()
    clamped = [r for r in rows if r.model == "beta"]
    assert len(clamped) == 2  # the partial fill, then the final fill
    assert all(r.verdict == "CLAMP" for r in clamped)
    assert clamped[0].partial is True
    assert clamped[1].partial is False
    assert clamped[0].fill_qty == Decimal("4")
    assert clamped[1].fill_qty == Decimal("2")


def test_blotter_approve_row_carries_fill_and_pnl() -> None:
    rows = StateReader(_blotter_log().records).blotter()
    approved = [r for r in rows if r.model == "alpha" and r.verdict == "APPROVE"]
    assert len(approved) == 1
    r = approved[0]
    assert r.fill_qty == Decimal("3")
    assert r.fill_px == Decimal("99")
    assert r.sim_pnl is not None  # a BUY fee-only delta -- negative, but present


def test_blotter_rows_are_ordered_oldest_first_by_seq() -> None:
    rows = StateReader(_blotter_log().records).blotter()
    assert rows == sorted(rows, key=lambda r: r.seq)


def test_blotter_after_seq_is_incremental() -> None:
    reader = StateReader(_blotter_log().records)
    everything = reader.blotter(after_seq=0, limit=100000)
    highest = everything[-1].seq
    assert reader.blotter(after_seq=highest) == []


def test_reconciliation_matches_model_cells_position_and_pnl() -> None:
    reader = StateReader(_blotter_log().records)
    recon = {r.model_id: r for r in reader.reconciliation()}
    assert set(recon) == {"alpha", "beta"}
    # alpha: bought 3 @ 99, no sells -> net position +3
    assert recon["alpha"].net_qty == Decimal("3")
    assert recon["alpha"].n_trades == 1
    # beta: sold 4 then 2 (short) -> net position -6
    assert recon["beta"].net_qty == Decimal("-6")
    assert recon["beta"].n_trades == 2


def test_blotter_empty_state_reason_warming_up_with_no_bars() -> None:
    reader = StateReader([])
    snap = reader.snapshot()
    expected = "Warming up -- waiting for the first bars to arrive."
    assert blotter_empty_state_reason(snap, []) == expected


def test_blotter_empty_state_reason_none_when_rows_present() -> None:
    reader = StateReader(_blotter_log().records)
    rows = reader.blotter()
    assert blotter_empty_state_reason(reader.snapshot(), rows) is None


def test_blotter_empty_state_reason_explains_sandbox_exploration() -> None:
    # bars are flowing (data_health has bars_seen > 0) but nothing has
    # promoted/traded yet -- an empty blotter should say why, not go blank.
    reader = _reader()  # the real backtest fixture: bars flow, models trade
    snap = reader.snapshot()
    reason = blotter_empty_state_reason(snap, [])  # force the "no rows" branch
    assert reason is not None
    assert "sandbox" in reason or "watching" in reason


# -- "Engine Room" conversation (docs/13 M21) -------------------------------


def _conversation_log() -> AuditLog:
    """One full loop iteration: Strategist proposes -> Optimizer runs
    trials -> Judge fails it -> Autopilot narrates -> a human KILLs ->
    Risk de-risks -> a separate candidate gets promoted."""
    log = AuditLog()
    seq = 1

    log.append(
        event_type="HypothesisEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=HypothesisEvent(
            hypo_id="h1",
            rationale="Volatility on BTC is climbing -- test wider breakout lookbacks.",
            target_models=["breakout_x"], proposed_space={}, regime="trending",
        ),
    )
    seq += 1
    for i, (metric, lookback) in enumerate([(0.8, 20), (1.42, 48), (1.1, 80)]):
        log.append(
            event_type="TrialEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=TrialEvent(
                trial_id=f"t{i}", hypo_id="h1", study_id="s1", params={"lookback": lookback},
                oos_metric=metric, seed=1, index=i,
            ),
        )
        seq += 1
    log.append(
        event_type="ValidationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=ValidationEvent(
            candidate_id="cand:breakout_x:1", result="FAIL", dsr=0.10, pbo=0.71,
            cost_survived=True, beats_equal_weight=False, evidence={"n_trials": 3},
        ),
    )
    seq += 1
    log.append(
        event_type="NarrationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=NarrationEvent(
            text="Discarding this idea, logging the hypothesis, moving on to mean-reversion."
        ),
    )
    seq += 1
    log.append(
        event_type="ControlEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=ControlEvent(command="KILL", source="ui", operator="alice", note="manual halt"),
    )
    seq += 1
    log.append(
        event_type="DeRiskEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=DeRiskEvent(reason="drawdown breach", models=["breakout_x"], action="PAUSE"),
    )
    seq += 1
    log.append(
        event_type="PromotionEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=PromotionEvent(
            candidate_id="cand:trend_ma_cross:1", from_book="sandbox", to_book="tracked",
            config_version="v1",
        ),
    )
    return log


def test_conversation_has_one_turn_per_participant_role() -> None:
    messages = StateReader(_conversation_log().records).conversation().messages
    participants = [m.participant for m in messages]
    expected = ["Strategist", "Optimizer", "Judge", "Autopilot", "Risk", "Risk", "Judge"]
    assert participants == expected


def test_conversation_optimizer_card_summarizes_best_trial_not_each_one() -> None:
    messages = StateReader(_conversation_log().records).conversation().messages
    optimizer = next(m for m in messages if m.participant == "Optimizer")
    assert "3 trials" in optimizer.text
    assert "1.42" in optimizer.text  # the best oos_metric, not the first/last
    assert "lookback=48" in optimizer.text
    # no cryptic internal IDs in the default text
    assert "h1" not in optimizer.text and "t0" not in optimizer.text and "s1" not in optimizer.text


def test_conversation_judge_message_carries_verdict_for_ui_coloring() -> None:
    messages = StateReader(_conversation_log().records).conversation().messages
    judge_cards = [m for m in messages if m.participant == "Judge" and m.kind == "card"]
    assert len(judge_cards) == 1
    assert judge_cards[0].verdict == "FAIL"
    assert "DSR 0.10" in judge_cards[0].text and "PBO 0.71" in judge_cards[0].text


def test_conversation_only_judge_messages_ever_carry_a_verdict() -> None:
    # matches the safety model: only the Judge/Validator sets a verdict
    messages = StateReader(_conversation_log().records).conversation().messages
    for m in messages:
        if m.verdict is not None:
            assert m.participant == "Judge"


def test_conversation_kill_and_derisk_appear_as_messages() -> None:
    messages = StateReader(_conversation_log().records).conversation().messages
    risk_messages = [m for m in messages if m.participant == "Risk"]
    assert any("Kill" in m.text and "alice" in m.text for m in risk_messages)
    assert any("De-risking" in m.text and "drawdown breach" in m.text for m in risk_messages)


def test_conversation_promotion_is_attributed_to_the_judge_not_the_strategist() -> None:
    # "the Judge is visibly the one who decides" (docs/13 M21 honesty bullet)
    messages = StateReader(_conversation_log().records).conversation().messages
    promotion = next(m for m in messages if "Promoted" in m.text)
    assert promotion.participant == "Judge"
    assert "trend_ma_cross" in promotion.text


def test_conversation_replays_deterministically_at_an_earlier_seq() -> None:
    reader = StateReader(_conversation_log().records)
    full = reader.conversation()
    mid = reader.conversation(at_seq=3)  # partway through the trials
    assert mid.max_seq == full.max_seq  # max_seq always reflects the whole log
    assert len(mid.messages) == 2  # Strategist + a partial Optimizer summary
    assert "trials" in mid.messages[1].text
    # replaying the same at_seq twice is byte-identical (determinism)
    again = reader.conversation(at_seq=3)
    assert mid == again


def test_conversation_no_raw_json_or_cryptic_ids_in_default_text() -> None:
    messages = StateReader(_conversation_log().records).conversation().messages
    for m in messages:
        assert "{" not in m.text and "}" not in m.text
        assert "cand:" not in m.text and "hypo_id" not in m.text


def test_conversation_works_from_templated_narration_without_an_llm() -> None:
    # NarrationEvent.text is read as-is regardless of which narrator wrote
    # it (RuleBased or Ollama) -- the feed never depends on the LLM being
    # present to produce a message.
    messages = StateReader(_conversation_log().records).conversation().messages
    autopilot = next(m for m in messages if m.participant == "Autopilot")
    expected = "Discarding this idea, logging the hypothesis, moving on to mean-reversion."
    assert autopilot.text == expected


def test_conversation_is_empty_and_valid_when_the_audit_log_has_no_autonomy_events() -> None:
    payload = StateReader([]).conversation()
    assert payload.messages == []
    assert payload.at_seq == 0 and payload.max_seq == 0
