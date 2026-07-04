"""Dev-only timing harness for the performance work (not shipped behavior).

Synthesizes a large, realistic audit log (the event mix `lqe live` produces:
one MarketEvent per bar, per-model SignalEvents, a slice of intent/decision/
order/fill chains, one aggregate RiskStateEvent per bar) and times the hot
paths the optimization phases target:

- StateReader construction + first/second snapshot()/blotter()/tape()/charts
- merged_records() full merge (and IncrementalMerge.extend once it exists)
- AuditLog.write_jsonl full rewrite (and append_jsonl once it exists)
- one IndicatorRuleAdapter.on_market call at short vs long history

Run before any optimization lands to record the baseline, then after each
phase:  ./.venv/Scripts/python.exe scripts/perf_probe.py
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lqe.core.clock import ManualClock  # noqa: E402
from lqe.core.context import Context  # noqa: E402
from lqe.core.engine import Engine  # noqa: E402
from lqe.core.events import (  # noqa: E402
    FillEvent,
    MarketEvent,
    Order,
    OrderIntent,
    RiskDecision,
    RiskStateEvent,
    SignalEvent,
)
from lqe.live.merge import merged_records  # noqa: E402
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter  # noqa: E402
from lqe.storage.state_reader import CatalogModelInfo, StateReader  # noqa: E402

N_MODELS = 104
N_BARS = 700  # ~100k records with the event mix below
TRADING_MODELS = 10  # models that fire an intent chain on a given bar
REPEATS = 5


def _median_ms(fn: Callable[[], object], repeats: int = REPEATS) -> float:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def _bar(i: int, start: datetime) -> MarketEvent:
    px = Decimal(100 + (i % 50))
    return MarketEvent(
        exchange="synthetic", symbol="BTC-USDT", timeframe="1m",
        ts_open=start + timedelta(minutes=i),
        o=px, h=px + 1, l=px - 1, c=px, v=10.0, source_version="perf",
    )


def build_synthetic_engine() -> tuple[Engine, list[MarketEvent]]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = ManualClock(start)
    engine = Engine(run_id="perf-probe", book="sandbox", clock=clock)
    bars: list[MarketEvent] = []
    for i in range(N_BARS):
        bar = _bar(i, start)
        bars.append(bar)
        clock.set(bar.ts_open)
        engine.emit("MarketEvent", bar)
        for m in range(N_MODELS):
            name = f"model_{m}"
            engine.emit(
                "SignalEvent",
                SignalEvent(
                    strategy=name, symbol="BTC-USDT",
                    direction="LONG" if (i + m) % 2 == 0 else "FLAT",
                    strength=1.0, intent_kind="ENTER", bar_ts=bar.ts_open, reason="perf",
                ),
            )
        for m in range(TRADING_MODELS):
            name = f"model_{m}"
            intent_id = f"i-{i}-{m}"
            order_id = f"o-{i}-{m}"
            engine.emit(
                "OrderIntent",
                OrderIntent(
                    intent_id=intent_id, signal_ref=f"s-{i}-{m}", strategy=name,
                    symbol="BTC-USDT", side="BUY" if i % 2 == 0 else "SELL",
                    qty=Decimal("0.01"), order_type="MARKET",
                    idempotency_key=intent_id, reason="perf",
                ),
            )
            engine.emit(
                "RiskDecision",
                RiskDecision(intent_ref=intent_id, verdict="APPROVE", approved_qty=Decimal("0.01")),
            )
            engine.emit(
                "Order",
                Order(
                    order_id=order_id, intent_ref=intent_id,
                    side="BUY" if i % 2 == 0 else "SELL", qty=Decimal("0.01"),
                    order_type="MARKET", status="FILLED",
                ),
            )
            engine.emit(
                "FillEvent",
                FillEvent(
                    order_id=order_id, fill_ts=bar.ts_open, fill_px=bar.c,
                    fill_qty=Decimal("0.01"), fee=Decimal("0.01"), slippage_bps=1.0, partial=False,
                ),
            )
        engine.emit(
            "RiskStateEvent",
            RiskStateEvent(
                equity=Decimal(10000 + i), cash=Decimal(9000), daily_pnl=Decimal(i),
                gross_exposure=Decimal(1000), peak_equity=Decimal(10000 + i),
                drawdown=0.01, open_orders=0, kill_active=False,
            ),
        )
    return engine, bars


def probe_state_reader(engine: Engine) -> None:
    records = engine.audit.records
    catalog = [
        CatalogModelInfo(model_id=f"model_{m}", family="trend", sleeve="trend_momentum")
        for m in range(N_MODELS)
    ]
    print(f"records: {len(records)}")
    construct = _median_ms(lambda: StateReader(records, catalog=catalog))
    print(f"StateReader construction:      {construct:10.2f} ms")

    reader = StateReader(records, catalog=catalog)
    t0 = time.perf_counter()
    reader.snapshot()
    print(f"first snapshot():              {(time.perf_counter() - t0) * 1000:10.2f} ms")
    print(f"repeat snapshot():             {_median_ms(reader.snapshot):10.2f} ms")
    hi = records[-1].seq - 60
    tape = _median_ms(lambda: reader.tape(after_seq=hi, limit=60))
    print(f"tape(after_seq=hi, limit=60):  {tape:10.2f} ms")
    blotter = _median_ms(lambda: reader.blotter(limit=60))
    print(f"blotter(limit=60):             {blotter:10.2f} ms")
    price = _median_ms(lambda: reader.price_series("BTC-USDT"))
    print(f"price_series():                {price:10.2f} ms")
    print(f"equity_curve():                {_median_ms(reader.equity_curve):10.2f} ms")


def probe_merge_and_persist(engine: Engine) -> None:
    merge = _median_ms(lambda: merged_records(engine))
    print(f"merged_records() full:         {merge:10.2f} ms")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "audit.jsonl"
        full = _median_ms(lambda: engine.audit.write_jsonl(out))
        print(f"write_jsonl() full:            {full:10.2f} ms")
        append = getattr(engine.audit, "append_jsonl", None)
        if append is not None:
            out2 = Path(td) / "audit2.jsonl"
            n = len(engine.audit.records)
            engine.audit.write_jsonl(out2)
            tail = _median_ms(lambda: append(out2, start=n - 150))
            print(f"append_jsonl() 150-rec tail:   {tail:10.2f} ms")
        else:
            print("append_jsonl():                 (not implemented yet)")


def _one_probe_adapter(n_hist: int, ctx: Context, start: datetime) -> None:
    adapter = IndicatorRuleAdapter(
        symbol="BTC-USDT", preset="macd_trend", name="perf_macd",
        params={"fast": 12, "slow": 26, "signal": 9},
    )
    adapter.on_start(ctx)
    for i in range(n_hist):
        adapter.on_market(_bar(i, start), ctx)
    last = _bar(n_hist, start)
    per_bar = _median_ms(lambda: adapter.on_market(last, ctx))
    print(f"on_market() @ {n_hist:>6} bars hist: {per_bar:8.2f} ms")


def probe_adapter(bars: list[MarketEvent]) -> None:
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for n_hist in (3_000, 30_000):
        _one_probe_adapter(n_hist, ctx, start)


def main() -> None:
    print("== perf_probe: synthesizing session ==")
    t0 = time.perf_counter()
    engine, bars = build_synthetic_engine()
    print(f"synthesis: {(time.perf_counter() - t0):.1f}s "
          f"({N_BARS} bars x {N_MODELS} models -> {len(engine.audit.records)} records)")
    print("\n== read path (StateReader) ==")
    probe_state_reader(engine)
    print("\n== poll path (merge + persist) ==")
    probe_merge_and_persist(engine)
    print("\n== adapter per-bar cost ==")
    probe_adapter(bars)


if __name__ == "__main__":
    main()
