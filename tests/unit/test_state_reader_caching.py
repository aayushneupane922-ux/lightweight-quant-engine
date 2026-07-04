"""Perf phase 1: StateReader memoizes its full-log replay (post-v4.0).

A StateReader instance is immutable (its record list is fixed at
construction), so every derived view is computed at most once per instance
-- the desk's 2-second WebSocket frame previously replayed the ENTIRE audit
log 3x per frame (snapshot + tape + blotter), which made hours-long live
sessions progressively slower. These tests pin the memoization contract:
same outputs, exactly one reconstruction walk.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

import lqe.storage.state_reader as sr_module
from lqe.core.clock import ManualClock
from lqe.core.engine import Engine
from lqe.core.events import (
    FillEvent,
    MarketEvent,
    Order,
    OrderIntent,
    RiskDecision,
    RiskStateEvent,
    SignalEvent,
)
from lqe.storage.state_reader import CatalogModelInfo, StateReader


def _engine_with_session(n_bars: int = 12) -> Engine:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = ManualClock(start)
    engine = Engine(run_id="cache-test", book="sandbox", clock=clock)
    for i in range(n_bars):
        ts = start + timedelta(minutes=i)
        clock.set(ts)
        px = Decimal(100 + i)
        engine.emit(
            "MarketEvent",
            MarketEvent(
                exchange="x", symbol="BTC-USDT", timeframe="1m", ts_open=ts,
                o=px, h=px + 1, l=px - 1, c=px, v=1.0, source_version="t",
            ),
        )
        engine.emit(
            "SignalEvent",
            SignalEvent(
                strategy="trend_ma_cross", symbol="BTC-USDT", direction="LONG",
                strength=1.0, intent_kind="ENTER", bar_ts=ts, reason="t",
            ),
        )
        intent_id = f"i{i}"
        engine.emit(
            "OrderIntent",
            OrderIntent(
                intent_id=intent_id, signal_ref=f"s{i}", strategy="trend_ma_cross",
                symbol="BTC-USDT", side="BUY", qty=Decimal("0.01"),
                order_type="MARKET", idempotency_key=intent_id, reason="t",
            ),
        )
        engine.emit(
            "RiskDecision",
            RiskDecision(intent_ref=intent_id, verdict="APPROVE", approved_qty=Decimal("0.01")),
        )
        engine.emit(
            "Order",
            Order(
                order_id=f"o{i}", intent_ref=intent_id, side="BUY",
                qty=Decimal("0.01"), order_type="MARKET", status="FILLED",
            ),
        )
        engine.emit(
            "FillEvent",
            FillEvent(
                order_id=f"o{i}", fill_ts=ts, fill_px=px, fill_qty=Decimal("0.01"),
                fee=Decimal("0.001"), slippage_bps=1.0, partial=False,
            ),
        )
        engine.emit(
            "RiskStateEvent",
            RiskStateEvent(
                equity=Decimal(10000 + i), cash=Decimal(9000), daily_pnl=Decimal(i),
                gross_exposure=Decimal(100), peak_equity=Decimal(10000 + i),
                drawdown=0.0, open_orders=0, kill_active=False,
            ),
        )
    return engine

def _reader(engine: Engine) -> StateReader:
    catalog = [CatalogModelInfo(model_id="trend_ma_cross", family="trend", sleeve="trend_momentum")]
    return StateReader(engine.audit.records, catalog=catalog)


@pytest.fixture()
def recon_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count _Reconstruction constructions without changing behavior."""
    calls: list[int] = []
    original = sr_module._Reconstruction.__init__

    def counting_init(self: Any, *args: Any, **kwargs: Any) -> None:
        calls.append(1)
        original(self, *args, **kwargs)

    monkeypatch.setattr(sr_module._Reconstruction, "__init__", counting_init)
    return calls


def test_snapshot_blotter_reconciliation_share_one_reconstruction(
    recon_counter: list[int],
) -> None:
    reader = _reader(_engine_with_session())
    first = reader.snapshot()
    second = reader.snapshot()
    reader.blotter(limit=10)
    reader.blotter(after_seq=5, limit=10)
    reader.reconciliation()
    assert first == second
    assert sum(recon_counter) == 1, (
        f"expected exactly one full-log reconstruction per reader, got {sum(recon_counter)}"
    )


def test_graph_at_latest_seq_reuses_the_cached_reconstruction(recon_counter: list[int]) -> None:
    reader = _reader(_engine_with_session())
    reader.snapshot()
    reader.graph()  # at_seq=None -> the full-log view, same reconstruction
    assert sum(recon_counter) == 1
    # the scrubber path (an explicit earlier at_seq) still builds its own
    reader.graph(at_seq=3)
    assert sum(recon_counter) == 2


def test_cached_snapshot_equals_a_fresh_readers_snapshot() -> None:
    engine = _engine_with_session()
    reader = _reader(engine)
    reader.blotter()  # populate caches in a different order first
    cached = reader.snapshot()
    fresh = _reader(engine).snapshot()
    assert cached == fresh


def test_tape_tail_scan_matches_naive_filter_for_all_windows() -> None:
    engine = _engine_with_session()
    reader = _reader(engine)
    records = engine.audit.records
    max_seq = records[-1].seq
    for after_seq in (0, 1, 5, max_seq // 2, max_seq - 1, max_seq, max_seq + 10):
        for limit in (1, 3, 60, len(records), len(records) + 50):
            expected_seqs = [r.seq for r in records if r.seq > after_seq][-limit:]
            got = reader.tape(after_seq=after_seq, limit=limit)
            assert [r.seq for r in got] == expected_seqs, (after_seq, limit)


def test_price_and_equity_series_are_computed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine_with_session()
    reader = _reader(engine)
    p1 = reader.price_series("BTC-USDT")
    e1 = reader.equity_curve()
    # Once cached, even wiping the raw record list can't change the results:
    # proof the repeat calls never rescan.
    monkeypatch.setattr(reader, "_records", [])
    assert reader.price_series("BTC-USDT") == p1
    assert reader.equity_curve() == e1
    assert len(p1) == 12
    assert len(e1) == 12


def test_downsampling_still_applies_per_call_on_the_cached_series() -> None:
    reader = _reader(_engine_with_session(n_bars=50))
    full = reader.price_series("BTC-USDT", max_points=1000)
    small = reader.price_series("BTC-USDT", max_points=10)
    assert len(full) == 50
    assert len(small) <= 10
    assert small[0] == full[0] and small[-1] == full[-1]


# --- StateReader.extended (perf phase 2b) -----------------------------------
# The live loop extends the previous poll's reader with just the new
# records instead of replaying the whole log. Contract: a chain of
# .extended() calls is observationally identical to one big fresh reader,
# and extending never mutates the old reader.


def _assert_readers_equal(a: StateReader, b: StateReader) -> None:
    assert a.snapshot() == b.snapshot()
    assert a.blotter() == b.blotter()
    assert a.blotter(after_seq=10, limit=5) == b.blotter(after_seq=10, limit=5)
    assert a.reconciliation() == b.reconciliation()
    assert a.tape(limit=1000) == b.tape(limit=1000)
    assert a.price_series("BTC-USDT") == b.price_series("BTC-USDT")
    assert a.equity_curve() == b.equity_curve()
    assert a.graph() == b.graph()


@pytest.mark.parametrize("batch_sizes", [[1] * 6, [2, 3, 1], [5, 1], [3, 3]])
def test_chained_extended_equals_one_big_reader(batch_sizes: list[int]) -> None:
    engine = _engine_with_session(n_bars=sum(batch_sizes) + 2)
    records = engine.audit.records
    catalog = [CatalogModelInfo(model_id="trend_ma_cross", family="trend", sleeve="trend_momentum")]

    per_bar = 7  # events emitted per bar by _engine_with_session
    cut = 2 * per_bar
    reader = StateReader(records[:cut], catalog=catalog)
    reader.snapshot()  # materialize the reconstruction so extended() carries it
    reader.price_series("BTC-USDT")
    reader.equity_curve()
    for size in batch_sizes:
        reader = reader.extended(records[cut : cut + size * per_bar])
        cut += size * per_bar

    fresh = StateReader(records, catalog=catalog)
    _assert_readers_equal(reader, fresh)


def test_extended_without_materialized_caches_still_matches() -> None:
    engine = _engine_with_session(n_bars=8)
    records = engine.audit.records
    catalog = [CatalogModelInfo(model_id="trend_ma_cross", family="trend", sleeve="trend_momentum")]
    reader = StateReader(records[:28], catalog=catalog)  # nothing read yet
    extended = reader.extended(records[28:])
    _assert_readers_equal(extended, StateReader(records, catalog=catalog))


def test_extended_does_not_mutate_the_old_reader() -> None:
    engine = _engine_with_session(n_bars=6)
    records = engine.audit.records
    catalog = [CatalogModelInfo(model_id="trend_ma_cross", family="trend", sleeve="trend_momentum")]
    old = StateReader(records[:21], catalog=catalog)
    before_snapshot = old.snapshot()
    before_tape = old.tape(limit=1000)
    before_price = old.price_series("BTC-USDT")

    extended = old.extended(records[21:])
    assert extended.snapshot() != before_snapshot  # new state really differs...
    assert old.snapshot() == before_snapshot  # ...but the old reader is frozen
    assert old.tape(limit=1000) == before_tape
    assert old.price_series("BTC-USDT") == before_price


def test_extended_model_state_fired_tracks_the_new_max_seq() -> None:
    # A model whose last fill was the final record reads FIRED; after
    # extending with newer records it must fall back to LONG -- the exact
    # regression the fired_on_last_seq -> last_fill_seq refactor guards.
    engine = _engine_with_session(n_bars=4)
    records = engine.audit.records
    catalog = [CatalogModelInfo(model_id="trend_ma_cross", family="trend", sleeve="trend_momentum")]

    fill_seqs = [r.seq for r in records if r.type == "FillEvent"]
    at_fill = StateReader(records[: fill_seqs[-1]], catalog=catalog)
    cell = {m.model_id: m for m in at_fill.snapshot().models}["trend_ma_cross"]
    assert cell.state == "FIRED"

    extended = at_fill.extended(records[fill_seqs[-1] :])
    fresh = StateReader(records, catalog=catalog)
    ext_cell = {m.model_id: m for m in extended.snapshot().models}["trend_ma_cross"]
    fresh_cell = {m.model_id: m for m in fresh.snapshot().models}["trend_ma_cross"]
    assert ext_cell == fresh_cell
