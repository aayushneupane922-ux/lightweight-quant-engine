"""Perf phase 3: the autonomy step runs on a background worker (queued,
in-order, exactly-once) instead of blocking bar processing for its full
8-30s+ of Optuna trials/validation/LLM calls -- and the desk's state
refresh now happens BEFORE the step is scheduled, so the UI shows fresh
bars during it.

Determinism contract: one single-thread worker + FIFO submission + a bar
snapshot captured at scheduling time means step count, order, per-step
inputs, and seeds all match the old synchronous schedule exactly; only
completion time shifts. The orchestrator's own (never-persisted) audit
chain and the trade chain must therefore be run-to-run identical, same as
the pre-existing orchestrator determinism tests.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from lqe.core.events import MarketEvent
from lqe.data.csv_replay import CsvReplayAdapter
from lqe.live.session import LiveSession, LiveSessionConfig
from lqe.risk.kill_switch import KillSwitch

pytest.importorskip("fastapi")
pytest.importorskip("optuna")

SYMBOL = "BTC-USDT"
N_SEED_BARS = 80


def _fixture_csv(tmp_path: Path) -> Path:
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(N_SEED_BARS):
        ts = now - timedelta(minutes=(N_SEED_BARS - i) + 5)
        close = 100.0 + 0.01 * i
        high = max(price, close) + 0.5
        low = min(price, close) - 0.5
        rows.append(f"{ts.isoformat()},{price:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + i % 5}")
        price = close
    path = tmp_path / "live_fixture.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _session(tmp_path: Path, *, autonomy_every: int, csv_path: Path | None = None) -> LiveSession:
    session = LiveSession(
        adapter=CsvReplayAdapter(
            csv_path or _fixture_csv(tmp_path), exchange="demo", symbol=SYMBOL, timeframe="1m"
        ),
        kill_switch=KillSwitch(path=tmp_path / "kill.json"),
        config=LiveSessionConfig(
            symbol=SYMBOL, timeframe="1m", poll_seconds=0.0, lookback_bars=60,
            starting_cash=Decimal("10000"), autonomy_every=autonomy_every,
            n_trials=1, min_periods=50, use_llm=False,
        ),
    )
    assert session.setup()
    return session


def _new_bars(session: LiveSession, n: int) -> list[MarketEvent]:
    last = session.bars_so_far[-1]
    bars = []
    price = float(last.c)
    for i in range(1, n + 1):
        ts = last.ts_open + timedelta(minutes=i)
        close = price + 0.05 * i
        bars.append(
            MarketEvent(
                exchange="demo", symbol=SYMBOL, timeframe="1m", ts_open=ts,
                o=Decimal(str(round(price, 2))), h=Decimal(str(round(max(price, close) + 0.5, 2))),
                l=Decimal(str(round(min(price, close) - 0.5, 2))),
                c=Decimal(str(round(close, 2))), v=10.0, source_version="t",
            )
        )
    return bars


def test_bar_processing_returns_before_a_slow_step_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path, autonomy_every=1)
    real_step = session.orchestrator.step

    def slow_step(now: datetime) -> Any:
        time.sleep(1.5)
        return real_step(now=now)

    monkeypatch.setattr(session.orchestrator, "step", slow_step)

    t0 = time.perf_counter()
    summary = session._process_new_bars(_new_bars(session, 1))
    elapsed = time.perf_counter() - t0

    try:
        assert elapsed < 1.0, f"bar processing blocked on the step ({elapsed:.2f}s)"
        assert summary is None  # not done yet
        assert session.autonomy_running()
    finally:
        session.close()

    drained = session._drain_completed_step()
    assert drained is not None and drained.step_count == 1


def test_desk_state_refreshes_before_the_step_is_scheduled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path, autonomy_every=1)
    order: list[str] = []

    real_refresh = session._persist_and_refresh
    real_step = session.orchestrator.step

    def spying_refresh() -> None:
        order.append("refresh")
        real_refresh()

    def spying_step(now: datetime) -> Any:
        order.append("step")
        return real_step(now=now)

    monkeypatch.setattr(session, "_persist_and_refresh", spying_refresh)
    monkeypatch.setattr(session.orchestrator, "step", spying_step)

    session._process_new_bars(_new_bars(session, 1))
    session.close()
    assert order[0] == "refresh", f"desk refreshed only after the step: {order}"


def test_queued_steps_run_exactly_once_in_order_and_chains_are_deterministic(
    tmp_path: Path,
) -> None:
    shared_csv = _fixture_csv(tmp_path)  # ONE fixture: identical inputs for both runs

    def run(subdir: str) -> tuple[list[str], list[str], list[int]]:
        (tmp_path / subdir).mkdir()
        session = _session(tmp_path / subdir, autonomy_every=1, csv_path=shared_csv)
        step_counts: list[int] = []
        bars = _new_bars(session, 3)
        for bar in bars:  # one bar per poll batch -> 3 steps scheduled
            summary = session._process_new_bars([bar])
            if summary is not None:
                step_counts.append(summary.step_count)
        # keep "polling" (like the real loop would) until all 3 queued steps
        # finished -- close() would cancel queued-but-unstarted ones
        deadline = time.time() + 120
        while len(step_counts) < 3 and time.time() < deadline:
            drained = session._drain_completed_step()
            if drained is not None:
                step_counts.append(drained.step_count)
            else:
                time.sleep(0.05)
        session.close()
        trade_chain = [r.hash for r in session.trade_engine.audit.records]
        autonomy_chain = [r.hash for r in session.orchestrator.engine.audit.records]
        return trade_chain, autonomy_chain, step_counts

    trade_1, autonomy_1, steps_1 = run("run1")
    trade_2, autonomy_2, steps_2 = run("run2")

    assert steps_1 == [1, 2, 3]  # exactly once, in order
    assert steps_1 == steps_2
    assert len(autonomy_1) > 0  # steps really ran and audited
    assert autonomy_1 == autonomy_2  # deterministic despite the worker thread
    assert trade_1 == trade_2
