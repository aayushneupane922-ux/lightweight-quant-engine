#!/usr/bin/env python3
"""One-click local launcher for the Obsidian Desk (docs/10 M12; docs/13
M18 "zero-CLI" launch). Double-click (or `python run.py`) and land on a
ready dashboard -- no terminal interaction needed to operate the product.

    python run.py                 # setup -> serve -> open browser, one step
    python run.py --window        # native desktop window (needs pywebview)
    python run.py --port 8137

On first run, if `data/catalog.duckdb` doesn't exist yet, a small synthetic
demo dataset is ingested automatically (offline, no network) via the same
`JobManager.start_ingest` path the dashboard's own "Ingest demo data" button
uses -- so there's something to look at immediately without requiring the
user to do anything first. A later run with existing data skips this.

Both bind **127.0.0.1 only** -- the app has no auth because it is never
reachable off the loopback interface, and it can place no real order
(paper-only lockout, non-negotiable #1). The desktop window is optional and
imported lazily: without `pywebview` installed it degrades to a printed
localhost URL rather than failing.
"""

from __future__ import annotations

import argparse
import math
import threading
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DEFAULT_DATA_ROOT = _ROOT / "data"
_DEFAULT_KILL_SWITCH = _ROOT / "runs" / "kill.json"


def _seed_demo_csv(path: Path, *, n_bars: int = 400) -> None:
    """A small, offline, synthetic OHLCV fixture with real-time-relative
    timestamps (same pattern as tests/integration/test_cli_live.py's
    fixture) so both ingest's data-quality checks and a later `lqe live`
    session's "is this bar closed/recent" filtering treat it as genuine,
    current-looking data -- a fixed past date would look stale to both."""
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(n_bars):
        ts = now - timedelta(minutes=(n_bars - i) + 5)
        drift = 0.02 * i
        cycle = 4.0 * math.sin(i / 30.0)
        close = 100.0 + drift + cycle
        openp = price
        high = max(openp, close) + 0.5
        low = min(openp, close) - 0.5
        rows.append(
            f"{ts.isoformat()},{openp:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + (i % 5)}"
        )
        price = close
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _first_run_setup(launch_state, job_manager, root: Path) -> None:  # type: ignore[no-untyped-def]
    """Runs once, in a background thread, before the dashboard becomes
    reachable. Never prints to a terminal -- `launch_state.message` is what
    the onboarding page polls and displays instead."""
    catalog_path = root / "catalog.duckdb"
    if not catalog_path.exists():
        launch_state.message = "Preparing a small demo dataset..."
        demo_csv = root / "_onboarding_demo.csv"
        _seed_demo_csv(demo_csv)
        job_manager.start_ingest(
            adapter="csv", exchange="demo", symbol="BTC-USDT", timeframe="1m",
            root=str(root), csv_path=str(demo_csv),
        )
        deadline = time.time() + 30
        status_state = "running"
        while time.time() < deadline:
            status = next(s for s in job_manager.statuses() if s.name == "ingest")
            status_state = status.state
            if status_state in ("done", "error"):
                break
            time.sleep(0.1)
        if status_state == "error":
            launch_state.message = "Demo data setup hit a snag -- opening anyway."
        else:
            launch_state.message = "Demo dataset ready."
    launch_state.message = "Starting the engine..."
    launch_state.ready = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-click launcher for the Obsidian Desk (paper-only)."
    )
    parser.add_argument("--port", type=int, default=8137)
    parser.add_argument("--window", action="store_true", help="Native desktop window (pywebview).")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    parser.add_argument(
        "--root", default=str(_DEFAULT_DATA_ROOT), help="Data root for first-run setup."
    )
    parser.add_argument("--kill-switch", default=str(_DEFAULT_KILL_SWITCH))
    args = parser.parse_args(argv)

    from lqe.live.control import ControlPlane
    from lqe.ops.jobs import JobManager, LaunchState
    from lqe.risk.kill_switch import KillSwitch
    from lqe.storage.state_reader import StateReader
    from lqe.ui.app import BIND_HOST, serve
    from lqe.ui.data import DeskData

    kill_switch = KillSwitch(Path(args.kill_switch))
    control = ControlPlane(kill_switch=kill_switch)
    desk_data = DeskData(state_reader=StateReader([]), control=control)
    job_manager = JobManager(desk_data=desk_data, kill_switch=kill_switch)
    desk_data.jobs = job_manager
    launch_state = LaunchState(ready=False, message="Starting up...")

    root = Path(args.root)
    threading.Thread(
        target=_first_run_setup, args=(launch_state, job_manager, root), daemon=True
    ).start()

    url = f"http://{BIND_HOST}:{args.port}"
    threading.Thread(
        target=lambda: serve(desk_data, port=args.port, launch_state=launch_state), daemon=True
    ).start()
    print(f"Obsidian Desk -> {url}  (paper-only, localhost)")

    if args.window:
        try:
            import webview  # type: ignore[import-not-found]  # pywebview -- optional dep
        except ImportError:
            print("pywebview not installed; falling back to a browser tab.")
            print("  install it with:  pip install pywebview")
        else:
            webview.create_window("lightweight-quant-engine", url)
            webview.start()
            return 0

    if not args.no_browser:
        webbrowser.open(url)
    print("serving... press Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
