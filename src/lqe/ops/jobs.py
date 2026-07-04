"""Background job runner for the GUI (docs/13 M18): lets the dashboard
trigger ingest / backtest / live start-stop instead of requiring the CLI.

Every job here calls into the exact same functions the CLI already uses
(`data.ingest.ingest`, `backtest.runner.run_backtest`,
`live.session.LiveSession`) from a background thread -- this adds no new
order-construction path and no new capability; it's a different caller of
code that already exists, is already tested, and still only ever produces
an `Order` through `make_order` after a `RiskModel` decision.

This module deliberately lives in `ops/` (alongside `doctor`/`backup`), not
`ui/`, so `ui/app.py`/`ui/data.py` only ever import it as a single, opaque
type -- never `models`/`risk`/`execution`/`autonomy` directly. That is what
keeps `tests/safety/test_ui_boundary.py` green: it scans `ui/`'s own files
for forbidden imports, and this module isn't one of them.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from lqe.core.types import Symbol, Timeframe
from lqe.risk.kill_switch import KillSwitch
from lqe.ui.data import DeskData

JobState = Literal["idle", "running", "done", "error"]
JobName = Literal["ingest", "backtest", "live"]

_JOB_NAMES: tuple[JobName, ...] = ("ingest", "backtest", "live")


@dataclass(frozen=True)
class JobStatus:
    name: JobName
    state: JobState
    message: str
    updated_at: datetime


@dataclass
class LaunchState:
    """docs/13 M18: shared between the launcher's background first-run
    setup and the FastAPI app's onboarding middleware. A plain mutable
    attribute swap is fine here -- same single-writer (the setup thread) /
    many-readers (request handlers) pattern as `DeskData.set_state_reader`."""

    ready: bool = False
    message: str = "Starting up..."


class JobManager:
    """Runs long operations in background threads and reports plain-language
    status for the GUI to poll -- never raw stdout/stack traces (docs/13
    M18's onboarding/status-screen requirement applies here too)."""

    def __init__(self, *, desk_data: DeskData, kill_switch: KillSwitch) -> None:
        self._desk_data = desk_data
        self._kill_switch = kill_switch
        self._lock = threading.Lock()
        now = datetime.now(UTC)
        self._statuses: dict[JobName, JobStatus] = {
            name: JobStatus(name=name, state="idle", message="not started", updated_at=now)
            for name in _JOB_NAMES
        }
        self._live_stop = threading.Event()
        self._live_thread: threading.Thread | None = None

    def statuses(self) -> list[JobStatus]:
        with self._lock:
            return [self._statuses[name] for name in _JOB_NAMES]

    def _set(self, name: JobName, state: JobState, message: str) -> None:
        with self._lock:
            self._statuses[name] = JobStatus(
                name=name, state=state, message=message, updated_at=datetime.now(UTC)
            )

    def is_live_running(self) -> bool:
        with self._lock:
            return self._statuses["live"].state == "running"

    # -- ingest ---------------------------------------------------------

    def start_ingest(
        self, *, adapter: str, exchange: str, symbol: Symbol, timeframe: Timeframe,
        root: str = "data", csv_path: str | None = None,
    ) -> bool:
        """Returns False (a no-op) if an ingest is already running, rather
        than launching a second one on top of it."""
        with self._lock:
            if self._statuses["ingest"].state == "running":
                return False
        self._set("ingest", "running", f"Ingesting {symbol} {timeframe} from {exchange}...")

        def _run() -> None:
            try:
                from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
                from lqe.data.csv_replay import CsvReplayAdapter
                from lqe.data.ingest import ingest
                from lqe.storage.catalog import Catalog

                root_path = Path(root)
                root_path.mkdir(parents=True, exist_ok=True)
                data_adapter = (
                    CsvReplayAdapter(
                        Path(csv_path), exchange=exchange, symbol=symbol, timeframe=timeframe
                    )
                    if adapter == "csv" and csv_path
                    else CcxtMarketDataAdapter(exchange)
                )
                with Catalog(root_path / "catalog.duckdb") as catalog:
                    result = ingest(
                        data_adapter, exchange=exchange, symbol=symbol, timeframe=timeframe,
                        root=root_path, catalog=catalog,
                    )
                self._set(
                    "ingest", "done",
                    f"Ingested {result.rows} bars -> version {result.version_id[:12]}...",
                )
            except Exception as exc:  # noqa: BLE001 - a designed error state, not a stack trace
                self._set("ingest", "error", f"{type(exc).__name__}: {exc}")

        threading.Thread(target=_run, daemon=True).start()
        return True

    # -- backtest ---------------------------------------------------------

    def start_backtest(
        self, *, root: str, bundle: str, symbol: Symbol, fast: int = 12, slow: int = 48,
        starting_cash: float = 10_000.0,
    ) -> bool:
        with self._lock:
            if self._statuses["backtest"].state == "running":
                return False
        self._set("backtest", "running", f"Backtesting {symbol} over bundle {bundle!r}...")

        def _run() -> None:
            try:
                from lqe.backtest.runner import run_backtest
                from lqe.models.plugins.trend_ma_cross import TrendMaCross
                from lqe.storage.replay_bundle import load_bundle

                _, bars = load_bundle(Path(root), bundle)
                symbol_bars = [b for b in bars if b.symbol == symbol]
                if not symbol_bars:
                    self._set("backtest", "error", f"no bars for {symbol!r} in bundle {bundle!r}")
                    return
                strategy = TrendMaCross(symbol=symbol, fast=fast, slow=slow)
                session = run_backtest(
                    run_id=f"gui-backtest:{bundle}:{strategy.name}", symbol=symbol,
                    bars=symbol_bars, strategy=strategy,
                    starting_cash=Decimal(str(starting_cash)),
                )
                equity = session.accounting.equity({symbol: symbol_bars[-1].c})
                verifies = session.engine.audit.verify()
                self._set(
                    "backtest", "done",
                    f"Final equity {equity} over {len(symbol_bars)} bars "
                    f"(audit hash-chain verifies: {verifies})",
                )
            except Exception as exc:  # noqa: BLE001 - a designed error state, not a stack trace
                self._set("backtest", "error", f"{type(exc).__name__}: {exc}")

        threading.Thread(target=_run, daemon=True).start()
        return True

    # -- live ---------------------------------------------------------

    def start_live(
        self, *, adapter: str, exchange: str, csv_path: str | None, symbols: list[Symbol],
        timeframe: Timeframe, poll_seconds: float, lookback_bars: int, starting_cash: float,
        autonomy_every: int, n_trials: int, min_periods: int, use_llm: bool, llm_model: str,
        out_path: str | None,
    ) -> bool:
        if self.is_live_running():
            return False
        if not symbols:
            return False
        # `--adapter csv` (offline demos/tests) only ever feeds one
        # `CsvReplayAdapter`'s single symbol -- same restriction cli.py's
        # `_cmd_live` enforces, so the GUI can't silently start a
        # multi-symbol live session where 4 of 5 feeds are permanently
        # empty (logged as "missing" every cycle, but never surfaced here).
        if adapter == "csv" and len(symbols) != 1:
            self._set(
                "live", "error",
                "--adapter csv only feeds one symbol's CSV -- pick one symbol, or use ccxt "
                "for a real multi-symbol universe.",
            )
            return False
        self._live_stop.clear()
        self._set("live", "running", "Starting live session...")

        def _run() -> None:
            try:
                from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
                from lqe.data.csv_replay import CsvReplayAdapter
                from lqe.live.session import LiveSession, LiveSessionConfig

                data_adapter = (
                    CsvReplayAdapter(
                        Path(csv_path), exchange=exchange, symbol=symbols[0], timeframe=timeframe
                    )
                    if adapter == "csv" and csv_path
                    else CcxtMarketDataAdapter(exchange)
                )
                session = LiveSession(
                    adapter=data_adapter, kill_switch=self._kill_switch, desk_data=self._desk_data,
                    config=LiveSessionConfig(
                        symbols=symbols, timeframe=timeframe, poll_seconds=poll_seconds,
                        lookback_bars=lookback_bars, starting_cash=Decimal(str(starting_cash)),
                        autonomy_every=autonomy_every, n_trials=n_trials,
                        min_periods=min_periods, use_llm=use_llm, llm_model=llm_model,
                        out_path=Path(out_path) if out_path else None,
                    ),
                )
                if not session.setup():
                    self._set(
                        "live", "error",
                        "No bars returned -- check network/exchange/symbol (or ingest first).",
                    )
                    return
                resumed_note = " (resumed from a prior session)" if session.resumed else ""
                self._set(
                    "live", "running",
                    f"Live: {len(session.bars_so_far)} bars seeded, "
                    f"{len(session.catalog.all())} models trading{resumed_note}",
                )
                try:
                    while not self._live_stop.is_set():
                        if self._live_stop.wait(timeout=poll_seconds):
                            break  # stop was requested during the wait
                        result = session.poll_once()
                        if result.error:
                            self._set("live", "running", f"Poll error, retrying: {result.error}")
                            continue
                        if result.new_bars:
                            autonomy_note = (
                                " · autonomy step running" if session.autonomy_running() else ""
                            )
                            self._set(
                                "live", "running",
                                f"{len(session.bars_so_far)} bars processed; "
                                f"kill_active={self._kill_switch.active}{autonomy_note}",
                            )
                finally:
                    session.close()  # lets an in-flight background autonomy step finish
                self._set("live", "done", f"Stopped after {len(session.bars_so_far)} bars.")
            except Exception as exc:  # noqa: BLE001 - a designed error state, not a stack trace
                self._set("live", "error", f"{type(exc).__name__}: {exc}")

        thread = threading.Thread(target=_run, daemon=True)
        self._live_thread = thread
        thread.start()
        return True

    def stop_live(self) -> bool:
        if not self.is_live_running():
            return False
        self._live_stop.set()
        return True
