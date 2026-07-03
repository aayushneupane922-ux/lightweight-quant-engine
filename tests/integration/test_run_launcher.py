"""The one-click launcher `run.py` (docs/13 M18): first-run setup must
auto-ingest a small demo dataset when none exists, skip it when one already
does, and always end with `launch_state.ready = True` -- never leave the
onboarding screen stuck. Loaded via `importlib` since `run.py` is a
top-level script, not a package module.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("optuna")

_RUN_PY = Path(__file__).resolve().parents[2] / "run.py"


def _load_run_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lqe_run_launcher", _RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["lqe_run_launcher"] = module
    spec.loader.exec_module(module)
    return module


run_launcher = _load_run_module()


def test_run_py_exists_and_loads() -> None:
    assert _RUN_PY.exists()
    assert hasattr(run_launcher, "main")


def test_seed_demo_csv_produces_bars_ingest_accepts(tmp_path: Path) -> None:
    from lqe.data.csv_replay import CsvReplayAdapter
    from lqe.data.ingest import ingest
    from lqe.storage.catalog import Catalog

    csv_path = tmp_path / "demo.csv"
    run_launcher._seed_demo_csv(csv_path, n_bars=60)
    assert csv_path.exists()

    root = tmp_path / "data"
    root.mkdir()
    adapter = CsvReplayAdapter(csv_path, exchange="demo", symbol="BTC-USDT", timeframe="1m")
    with Catalog(root / "catalog.duckdb") as catalog:
        result = ingest(
            adapter, exchange="demo", symbol="BTC-USDT", timeframe="1m",
            root=root, catalog=catalog,
        )
    assert result.rows == 60  # passes §8.4 validation cleanly, nothing quarantined


def test_first_run_setup_ingests_when_no_catalog_exists(tmp_path: Path) -> None:
    from lqe.live.control import ControlPlane
    from lqe.ops.jobs import JobManager, LaunchState
    from lqe.risk.kill_switch import KillSwitch
    from lqe.storage.state_reader import StateReader
    from lqe.ui.data import DeskData

    root = tmp_path / "data"
    kill_switch = KillSwitch.in_memory()
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane(kill_switch=kill_switch))
    jobs = JobManager(desk_data=desk, kill_switch=kill_switch)
    launch_state = LaunchState(ready=False, message="Starting up...")

    run_launcher._first_run_setup(launch_state, jobs, root)

    assert launch_state.ready is True
    assert (root / "catalog.duckdb").exists()


def test_first_run_setup_skips_ingest_when_catalog_already_exists(tmp_path: Path) -> None:
    from lqe.live.control import ControlPlane
    from lqe.ops.jobs import JobManager, LaunchState
    from lqe.risk.kill_switch import KillSwitch
    from lqe.storage.catalog import Catalog
    from lqe.storage.state_reader import StateReader
    from lqe.ui.data import DeskData

    root = tmp_path / "data"
    root.mkdir()
    Catalog(root / "catalog.duckdb").close()  # pre-exists -- setup must not re-ingest

    kill_switch = KillSwitch.in_memory()
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane(kill_switch=kill_switch))
    jobs = JobManager(desk_data=desk, kill_switch=kill_switch)
    launch_state = LaunchState(ready=False, message="Starting up...")

    start = time.time()
    run_launcher._first_run_setup(launch_state, jobs, root)
    elapsed = time.time() - start

    assert launch_state.ready is True
    ingest_status = next(s for s in jobs.statuses() if s.name == "ingest")
    assert ingest_status.state == "idle"  # never triggered
    assert elapsed < 2.0  # no 30s ingest-wait loop was entered
