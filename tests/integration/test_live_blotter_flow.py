"""Docs/13 M20: "verify trades genuinely flow (fix the cause, not just the
view)". Runs the real live fleet (offline CSV adapter, same fixture seam as
`tests/integration/test_cli_live.py` / M18's job tests) and asserts fills
actually reach the blotter -- if the fleet legitimately produced nothing,
this test would fail loudly rather than let a silent display gap hide
behind a passing test suite.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lqe.live.control import ControlPlane
from lqe.ops.jobs import JobManager, JobStatus
from lqe.risk.kill_switch import KillSwitch
from lqe.storage.state_reader import BlotterRow, StateReader
from lqe.ui.data import DeskData

pytest.importorskip("fastapi")
pytest.importorskip("optuna")

SYMBOL = "BTC-USDT"
N_BARS = 200


def _fixture_csv(tmp_path: Path) -> Path:
    # A real up-then-down cycle (not a flat/monotone series) so momentum-
    # and mean-reversion-style models across the 50+ model catalog have an
    # honest reason to fire, not just a hand-tuned trigger for one model.
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(N_BARS):
        drift = 8.0 * ((i % 60) / 30.0 - 1.0)  # sawtooth: up 30 bars, down 30
        close = 100.0 + drift
        openp = price
        high = max(openp, close) + 0.5
        low = min(openp, close) - 0.5
        ts = now - timedelta(minutes=(N_BARS - i) + 5)
        rows.append(
            f"{ts.isoformat()},{openp:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + (i % 5)}"
        )
        price = close
    path = tmp_path / "blotter-flow.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _wait_for_message(
    manager: JobManager, name: str, substring: str, timeout: float = 15.0
) -> JobStatus:
    deadline = time.time() + timeout
    last: JobStatus | None = None
    while time.time() < deadline:
        last = next(s for s in manager.statuses() if s.name == name)
        if substring in last.message or last.state == "error":
            return last
        time.sleep(0.02)
    raise AssertionError(f"job {name!r} never showed {substring!r} in time; last={last}")


def test_live_fleet_produces_real_fills_that_reach_the_blotter(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    kill_switch = KillSwitch.in_memory()
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane(kill_switch=kill_switch))
    manager = JobManager(desk_data=desk, kill_switch=kill_switch)

    started = manager.start_live(
        adapter="csv", exchange="demo", csv_path=str(csv_path), symbol=SYMBOL, timeframe="1m",
        poll_seconds=0.02, lookback_bars=150, starting_cash=10_000.0, autonomy_every=1000,
        n_trials=1, min_periods=50, use_llm=False, llm_model="llama3.2:3b", out_path=None,
    )
    assert started is True

    running = _wait_for_message(manager, "live", "models trading")
    assert running.state == "running", running.message

    # Give the live loop a little wall-clock time to poll through the
    # remaining bars past the seeded lookback window.
    deadline = time.time() + 10.0
    rows: list[BlotterRow] = []
    while time.time() < deadline:
        rows = desk.blotter()
        if any(r.fill_qty is not None for r in rows):
            break
        time.sleep(0.1)

    manager.stop_live()

    fills = [r for r in rows if r.fill_qty is not None]
    assert fills, (
        "the live fleet ran but produced zero fills reaching the blotter -- "
        "this is exactly the M20 'display gap, not a trading gap' scenario "
        "this test exists to catch; if it fires, the cause is in the fleet, "
        "not the Blotter view"
    )
    # every fill traces back through a real risk decision, not a bypass
    assert all(r.verdict in ("APPROVE", "CLAMP") for r in fills)

    reconciliation = desk.reconciliation()
    traded_models = {r.model_id for r in reconciliation if r.n_trades > 0}
    assert traded_models, "reconciliation should show at least one model with trades"
