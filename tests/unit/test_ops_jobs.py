"""`JobManager` (docs/13 M18): the GUI's way to trigger ingest/backtest/live
start-stop from a background thread instead of requiring the CLI. Every job
calls the exact same already-tested functions the CLI uses -- these tests
prove that wiring actually works end to end, using the offline CSV adapter
seam (no real network) exactly like `tests/integration/test_cli_live.py`.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lqe.live.control import ControlPlane
from lqe.ops.jobs import JobManager, JobStatus
from lqe.risk.kill_switch import KillSwitch
from lqe.storage.state_reader import StateReader
from lqe.ui.data import DeskData

pytest.importorskip("fastapi")
pytest.importorskip("optuna")

SYMBOL = "BTC-USDT"
N_BARS = 150


def _fixture_csv(tmp_path: Path, name: str = "fixture.csv") -> Path:
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(N_BARS):
        ts = now - timedelta(minutes=(N_BARS - i) + 5)
        close = 100.0 + 0.01 * i
        openp = price
        high = max(openp, close) + 0.5
        low = min(openp, close) - 0.5
        rows.append(
            f"{ts.isoformat()},{openp:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + (i % 5)}"
        )
        price = close
    path = tmp_path / name
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _manager(tmp_path: Path) -> JobManager:
    kill_switch = KillSwitch.in_memory()
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane(kill_switch=kill_switch))
    return JobManager(desk_data=desk, kill_switch=kill_switch)


def _wait_for(
    manager: JobManager, name: str, states: tuple[str, ...], timeout: float = 10.0
) -> JobStatus:
    deadline = time.time() + timeout
    last: JobStatus | None = None
    while time.time() < deadline:
        last = next(s for s in manager.statuses() if s.name == name)
        if last.state in states:
            return last
        time.sleep(0.02)
    raise AssertionError(f"job {name!r} did not reach {states} in time; last={last}")


def _wait_for_message(
    manager: JobManager, name: str, substring: str, timeout: float = 10.0
) -> JobStatus:
    """Poll until the job's message contains `substring` or it errors out --
    distinct from `_wait_for` because "running" covers more than one phase
    here (setup vs. post-setup) and the test cares which phase it reached."""
    deadline = time.time() + timeout
    last: JobStatus | None = None
    while time.time() < deadline:
        last = next(s for s in manager.statuses() if s.name == name)
        if substring in last.message or last.state == "error":
            return last
        time.sleep(0.02)
    raise AssertionError(f"job {name!r} never showed {substring!r} in time; last={last}")


def test_statuses_start_idle() -> None:
    manager = _manager(Path("."))
    names = {s.name for s in manager.statuses()}
    assert names == {"ingest", "backtest", "live"}
    assert all(s.state == "idle" for s in manager.statuses())


def test_start_ingest_runs_the_real_ingest_pipeline(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    manager = _manager(tmp_path)
    root = tmp_path / "data"

    started = manager.start_ingest(
        adapter="csv", exchange="demo", symbol=SYMBOL, timeframe="1m",
        root=str(root), csv_path=str(csv_path),
    )
    assert started is True

    status = _wait_for(manager, "ingest", ("done", "error"))
    assert status.state == "done", status.message
    assert "Ingested" in status.message
    assert (root / "catalog.duckdb").exists()

    # a second ingest call while... (not running anymore) should be allowed
    # again -- only a genuinely in-flight job is refused.
    started_again = manager.start_ingest(
        adapter="csv", exchange="demo", symbol=SYMBOL, timeframe="1m",
        root=str(root), csv_path=str(csv_path),
    )
    assert started_again is True


def test_start_ingest_is_a_noop_while_already_running(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    manager = _manager(tmp_path)
    root = tmp_path / "data"
    assert manager.start_ingest(
        adapter="csv", exchange="demo", symbol=SYMBOL, timeframe="1m",
        root=str(root), csv_path=str(csv_path),
    )
    # Immediately try again before the background thread could plausibly
    # have finished -- must be refused, not double-launched.
    second = manager.start_ingest(
        adapter="csv", exchange="demo", symbol=SYMBOL, timeframe="1m",
        root=str(root), csv_path=str(csv_path),
    )
    _wait_for(manager, "ingest", ("done", "error"))
    assert second is False


def test_start_backtest_runs_the_real_backtest_pipeline(tmp_path: Path) -> None:
    from lqe.data.csv_replay import CsvReplayAdapter
    from lqe.data.ingest import ingest
    from lqe.storage.catalog import Catalog
    from lqe.storage.replay_bundle import build_bundle

    csv_path = _fixture_csv(tmp_path)
    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    adapter = CsvReplayAdapter(csv_path, exchange="demo", symbol=SYMBOL, timeframe="1m")
    with Catalog(root / "catalog.duckdb") as catalog:
        result = ingest(
            adapter, exchange="demo", symbol=SYMBOL, timeframe="1m", root=root, catalog=catalog
        )
    now = datetime.now(UTC)
    build_bundle(
        root, bundle_id="gui-bundle", exchange="demo", symbols=[SYMBOL], timeframe="1m",
        start=now - timedelta(days=1), end=now + timedelta(days=1), seed=1,
        source_versions=[result.version_id],
    )

    manager = _manager(tmp_path)
    started = manager.start_backtest(root=str(root), bundle="gui-bundle", symbol=SYMBOL)
    assert started is True
    status = _wait_for(manager, "backtest", ("done", "error"))
    assert status.state == "done", status.message
    assert "Final equity" in status.message
    assert "verifies: True" in status.message


def test_start_live_runs_and_stop_live_halts_it(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    manager = _manager(tmp_path)

    started = manager.start_live(
        adapter="csv", exchange="demo", csv_path=str(csv_path), symbol=SYMBOL, timeframe="1m",
        poll_seconds=0.05, lookback_bars=100, starting_cash=10_000.0, autonomy_every=1000,
        n_trials=1, min_periods=50, use_llm=False, llm_model="llama3.2:3b", out_path=None,
    )
    assert started is True
    assert manager.is_live_running() is True

    running = _wait_for_message(manager, "live", "models trading")
    assert running.state == "running", running.message
    assert "models trading" in running.message

    stopped = manager.stop_live()
    assert stopped is True
    _wait_for(manager, "live", ("done", "error"))
    assert manager.is_live_running() is False


def test_stop_live_is_a_noop_when_nothing_is_running(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.stop_live() is False


def test_start_live_is_a_noop_while_already_running(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    manager = _manager(tmp_path)
    assert manager.start_live(
        adapter="csv", exchange="demo", csv_path=str(csv_path), symbol=SYMBOL, timeframe="1m",
        poll_seconds=0.05, lookback_bars=100, starting_cash=10_000.0, autonomy_every=1000,
        n_trials=1, min_periods=50, use_llm=False, llm_model="llama3.2:3b", out_path=None,
    )
    second = manager.start_live(
        adapter="csv", exchange="demo", csv_path=str(csv_path), symbol=SYMBOL, timeframe="1m",
        poll_seconds=0.05, lookback_bars=100, starting_cash=10_000.0, autonomy_every=1000,
        n_trials=1, min_periods=50, use_llm=False, llm_model="llama3.2:3b", out_path=None,
    )
    assert second is False
    manager.stop_live()
    _wait_for(manager, "live", ("done", "error"))
