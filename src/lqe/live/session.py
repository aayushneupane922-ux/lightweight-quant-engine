"""`LiveSession` (docs/13 M18, multi-symbol per docs/15 M27's disclosed live
follow-up): the reusable core of `lqe live`, extracted from `cli._cmd_live`
so both the CLI and the new GUI-triggered job runner (`ops/jobs.py`) share
exactly one implementation rather than maintaining two.

Same seed/resume logic (docs/12 M15), same fleet/engine/orchestrator wiring,
same write-through persistence to `--out`, now generalized from one symbol
to a `Universe` of N symbols (docs/15's "one book/session/runner per
instrument" design, extended from the M27 backtest side to live): one
`LiveMultiModelRunner` per symbol, all sharing one `Engine`/audit log/kill
switch and one cross-book `PortfolioContext`, driven by `Universe.cycles()`
grouping each poll's merged, `ts_open`-sorted bars into synchronized
per-timestamp cycles -- a missing symbol this cycle means no-trade for it,
never a crash for the others (same as the M27 backtest runner). Only the
CLI-specific bits (print statements, browser-opening, the blocking main
loop) stay in `cli.py`/`ops/jobs.py`, which each drive this class
differently: the CLI loops synchronously with its own prints; the job
runner drives it from a background thread and reports status to the desk
instead of stdout.

Still paper-only end to end: `PaperBroker` is still the only
`ExecutionAdapter`, `make_order` is still the only `Order` constructor, and
one shared `KillSwitch` halts every model's new entries (across every
symbol) at once.

The Floor's model-grid UI reshape into "models x instruments" is explicitly
M28's job (docs/15), not this follow-up -- so the desk-facing catalog rows
here are deliberately drawn from just the primary (first) symbol's catalog,
same as the autonomy `Orchestrator`'s own search target, rather than
duplicating every model row once per symbol.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from lqe.autonomy.narrator import make_narrator
from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable_scaled import broad_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.clock import ManualClock
from lqe.core.engine import AuditLog, Engine
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.core.universe import Universe, UniverseCycle
from lqe.data.base import MarketDataAdapter
from lqe.live.control import ControlPlane
from lqe.live.merge import IncrementalMerge
from lqe.live.multi_model_runner import LiveMultiModelRunner, build_fleet
from lqe.live.multi_symbol_feed import MultiSymbolLiveFeed
from lqe.models.catalog import CatalogEntry, IntakeResult, ModelCatalog
from lqe.models.catalog_scale import build_scaled_catalog
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.risk.portfolio_context import PortfolioContext
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.data import CatalogRow, DeskData


def _market_events_by_symbol_from_audit(
    audit: AuditLog, symbols: list[Symbol]
) -> dict[Symbol, list[MarketEvent]]:
    """Decompose a persisted audit's flat `MarketEvent` history back into
    one chronological list per symbol, for `MultiSymbolLiveFeed.resume_from`
    -- each symbol keeps its own independent dedup cursor, same as a fresh
    seed. `MarketEvent`s are emitted in processing order (one per bar, per
    `_process_cycle`), so the audit's own seq order is already chronological
    within each symbol's bucket -- no re-sort needed."""
    result: dict[Symbol, list[MarketEvent]] = {sym: [] for sym in symbols}
    for envelope in audit.records:
        if envelope.type != "MarketEvent":
            continue
        bar = MarketEvent.model_validate(envelope.payload)
        result.setdefault(bar.symbol, []).append(bar)
    return result


def _catalog_rows(catalog: ModelCatalog) -> list[CatalogRow]:
    rows = [
        CatalogRow(
            model_id=e.manifest.id, family=e.manifest.family, sleeve=e.manifest.sleeve,
            one_liner=e.manifest.one_liner, oss_libs=list(e.manifest.oss_libs),
            status=e.manifest.status,
        )
        for e in catalog.all()
    ]
    rows += [
        CatalogRow(
            model_id=q.model_id, family="—", one_liner="", oss_libs=[],
            status="unproven", quarantined=True, quarantine_reason="; ".join(q.reasons),
        )
        for q in catalog.quarantined()
    ]
    return rows


@dataclass(frozen=True)
class LiveSessionConfig:
    symbols: list[Symbol]
    timeframe: Timeframe
    poll_seconds: float = 60.0
    lookback_bars: int = 300
    starting_cash: Decimal = Decimal("10000")
    autonomy_every: int = 5
    n_trials: int = 8
    min_periods: int = 200
    use_llm: bool = False
    llm_model: str = "llama3.2:3b"
    out_path: Path | None = None
    diversification_path: Path | None = None


@dataclass(frozen=True)
class AutonomyStepSummary:
    step_count: int
    focus_model: str
    verdict: str
    promoted: bool
    narration: str


@dataclass(frozen=True)
class PollResult:
    new_bars: int
    error: str | None = None
    autonomy_step: AutonomyStepSummary | None = None


class LiveSession:
    """One live-fleet session: every admitted catalog model trading against
    a real (or replayed) feed, sharing one audit log/kill switch/risk model,
    with the autonomy loop narrating alongside it. Call `setup()` once, then
    `poll_once()` repeatedly (the caller owns the loop/sleep/scheduling)."""

    def __init__(
        self, *, adapter: MarketDataAdapter, config: LiveSessionConfig, kill_switch: KillSwitch,
        desk_data: DeskData | None = None,
    ) -> None:
        self.config = config
        self.kill_switch = kill_switch
        self.feed = MultiSymbolLiveFeed.build(
            adapter=adapter, symbols=config.symbols, timeframe=config.timeframe,
            poll_seconds=config.poll_seconds,
        )
        # Tracks synchronized per-timestamp cycles across the whole universe
        # (docs/15 M27); reused for both the initial seed/resume history and
        # every later poll, so `last_seen`/missing-symbol bookkeeping
        # accumulates across the session's whole lifetime, not just one call.
        self._universe = Universe(list(config.symbols))
        self.bars_so_far: list[MarketEvent] = []
        self.resumed = False
        self._bars_since_step = 0
        self.step_count = 0
        # Perf phase 2: incremental per-poll work. `_merge` keeps the
        # persistent merged trade+autonomy view (only new records get merged
        # each poll); `_last_reader` is extended, not rebuilt; `_persisted`
        # is the audit-file cursor for append-only writes.
        self._merge = IncrementalMerge()
        self._last_reader: StateReader | None = None
        self._persisted = 0
        # Perf phase 3b: the autonomy step (Optuna trials + validation
        # backtests + optional LLM calls, 8-30s+) runs on this single
        # background worker instead of blocking bar processing. One worker +
        # FIFO submission means steps run exactly once, in order, each on
        # the bar snapshot captured when it came due -- the same step
        # count/inputs/seeds as a synchronous run; only completion time
        # shifts. Safe because the orchestrator appends only to its OWN
        # audit chain (never persisted, never replayed); the trade chain
        # stays poll-thread-only.
        self._autonomy_pool: ThreadPoolExecutor | None = None
        self._pending_steps: deque[Future[AutonomyStepSummary]] = deque()
        # `desk_data`, when given (docs/13 M18: the GUI job runner passes the
        # server's already-running DeskData so the dashboard updates in
        # place), is reused rather than built fresh -- its ControlPlane
        # (kill switch, autopilot flag) then persists across live sessions
        # started/stopped from the GUI, instead of resetting each time. The
        # CLI path leaves this None and gets a fresh DeskData, as before.
        self._desk_data: DeskData | None = desk_data

    @property
    def desk_data(self) -> DeskData:
        if self._desk_data is None:
            raise RuntimeError("LiveSession.setup() must run before desk_data is available")
        return self._desk_data

    def setup(self) -> bool:
        """Seed or resume history and build the fleet/engine/orchestrator.
        Returns False if no bars are available at all (caller should treat
        this as a startup failure, not silently proceed)."""
        out_path = self.config.out_path
        symbols = self.config.symbols
        history: list[MarketEvent]
        if out_path is not None and out_path.exists():
            prior_audit = AuditLog.from_jsonl(out_path)
            bars_by_symbol = _market_events_by_symbol_from_audit(prior_audit, symbols)
            history = sorted(
                (bar for bars in bars_by_symbol.values() for bar in bars),
                key=lambda b: b.ts_open,
            )
            self.resumed = True
            self.feed.resume_from(bars_by_symbol)
        else:
            history = self.feed.seed_history(lookback_bars=self.config.lookback_bars)
        if not history:
            return False

        risk_model = RiskModel(kill_switch=self.kill_switch)
        self.trade_clock = ManualClock(history[0].ts_open)
        self.trade_engine = Engine(run_id="live-fleet", book="sandbox", clock=self.trade_clock)
        self.portfolio_context = PortfolioContext()
        self._last_close: dict[Symbol, Decimal] = dict.fromkeys(symbols, Decimal("0"))

        self.catalogs: dict[Symbol, ModelCatalog] = {}
        self.catalog_results: dict[Symbol, list[IntakeResult]] = {}
        self.runners: dict[Symbol, LiveMultiModelRunner] = {}
        admitted_all: list[tuple[Symbol, CatalogEntry]] = []
        for sym in symbols:
            catalog, results = build_scaled_catalog(sym, universe=symbols)
            self.catalogs[sym] = catalog
            self.catalog_results[sym] = results
            admitted = catalog.all()
            admitted_all.extend((sym, e) for e in admitted)
            fleet = build_fleet(admitted, starting_cash=self.config.starting_cash)
            self.runners[sym] = LiveMultiModelRunner(
                engine=self.trade_engine, fleet=fleet, symbol=sym, risk_model=risk_model,
                portfolio_context=self.portfolio_context,
            )
        # First symbol's catalog is the primary/desk-facing one (see module
        # docstring) -- Floor's "models x instruments" reshape is M28's job.
        self.catalog = self.catalogs[symbols[0]]

        for cycle in self._universe.cycles(history):
            self._process_cycle(cycle)
        if out_path is not None:
            # one full (truncating) write at setup -- this is also the
            # resume-rewrite path; every later poll appends only the tail
            self.trade_engine.audit.write_jsonl(out_path)
            self._persisted = self.trade_engine.audit.record_count()

        self.orchestrator = Orchestrator(
            validator=Validator(),
            gate=PromotionGate(thresholds=GateThresholds(min_periods=self.config.min_periods)),
            optimizer=OptunaOptimizer(),
            searchable_models=broad_searchable_models(),
            bars=list(self.bars_so_far),
            symbol=symbols[0],
            starting_cash=self.config.starting_cash,
            run_id="live-fleet-autonomy",
            n_trials=self.config.n_trials,
            narrator=make_narrator(
                use_llm=self.config.use_llm, model=self.config.llm_model, seed=0, timeout_s=45.0
            ),
        )

        self._catalog_info = [
            # Every admitted model is author-declared "unproven" at intake
            # (models.manifest); only a gate PASS elsewhere ever sets
            # "validated". V5 M28: each entry is stamped with the symbol its
            # OWN per-symbol catalog was built for -- the Floor's "models x
            # instruments" reshape needs this to place an idle (never-
            # traded) admitted model's cell on the right instrument.
            CatalogModelInfo(
                model_id=e.manifest.id, family=e.manifest.family,
                sleeve=e.manifest.sleeve, status="unproven", symbol=sym,
            )
            for sym, e in admitted_all
        ]

        if self._desk_data is None:
            control = ControlPlane(kill_switch=self.kill_switch)
            self._desk_data = DeskData(
                state_reader=self._rebuild_state_reader(), control=control,
                catalog_rows=_catalog_rows(self.catalog),
                diversification_path=self.config.diversification_path,
            )
        else:
            self._desk_data.set_state_reader(self._rebuild_state_reader())
            self._desk_data.set_catalog_rows(_catalog_rows(self.catalog))
        return True

    def _portfolio_snapshot(
        self,
    ) -> tuple[dict[Symbol, Decimal], dict[Symbol, Decimal], dict[Symbol, str | None]]:
        """Cross-book/cross-symbol totals as of the END of the previous
        cycle (`self._last_close`), keyed by a synthetic `symbol::model_id`
        string per book -- `PortfolioContext.refresh()`'s `Mapping[Symbol,
        ...]` signature only cares that keys are strings and iterable, so
        this reuses it as-is for the live fleet's many-books-per-symbol
        shape (`Symbol` is a plain `str` alias) rather than widening that
        already-tested API. `.equity`/`.gross_notional` are sums over every
        value regardless of key naming; `_sleeve_notional` only reads the
        per-key sleeve, so per-book granularity here is correct."""
        book_equity: dict[Symbol, Decimal] = {}
        book_notional: dict[Symbol, Decimal] = {}
        book_sleeve: dict[Symbol, str | None] = {}
        for sym, runner in self.runners.items():
            price = self._last_close[sym]
            for book in runner.fleet:
                key = f"{sym}::{book.model_id}"
                book_equity[key] = book.accounting.equity({sym: price})
                book_notional[key] = abs(book.accounting.position_qty(sym)) * price
                book_sleeve[key] = book.sleeve
        return book_equity, book_notional, book_sleeve

    def _process_cycle(self, cycle: UniverseCycle) -> None:
        """One synchronized instant across the universe (docs/15 M27): tick
        once, refresh the shared `PortfolioContext` from state as of the
        *previous* cycle (no-look-ahead -- this cycle's intents are never
        checked against this cycle's own not-yet-happened fills, same
        guarantee a single book already has), then feed every bar in this
        cycle to every symbol's runner -- own-symbol bars get the full
        pipeline, foreign-symbol bars are observe-only (`process_bar`'s own
        dispatch). A symbol missing from `cycle.bars` this cycle simply
        contributes nothing -- no crash, no desync for the others."""
        self.trade_clock.set(cycle.ts_open)
        self.trade_engine.tick()
        book_equity, book_notional, book_sleeve = self._portfolio_snapshot()
        self.portfolio_context.refresh(
            book_equity=book_equity, book_notional=book_notional, book_sleeve=book_sleeve,
        )
        for bar in cycle.bars:
            self.trade_engine.emit("MarketEvent", bar)
            for runner in self.runners.values():
                runner.process_bar(bar)
            self._last_close[bar.symbol] = bar.c
            self.bars_so_far.append(bar)

    def _rebuild_state_reader(self) -> StateReader:
        new = self._merge.extend(self.trade_engine, self.orchestrator.engine)
        if self._last_reader is None or self._merge.last_extend_rebuilt:
            # first build, or the merge had to renumber its prefix -- a
            # carried-forward reader would be stale; start fresh.
            self._last_reader = StateReader(list(self._merge.merged), catalog=self._catalog_info)
        elif new:
            self._last_reader = self._last_reader.extended(new)
        return self._last_reader

    def poll_once(self) -> PollResult:
        """One poll cycle. Never raises on a transient feed error -- returns
        it in `PollResult.error` instead so a long-running caller (CLI loop
        or a background job thread) survives it and simply retries next
        cycle, same as the original `_cmd_live` behavior."""
        try:
            new_bars = self.feed.poll_new_bars()
        except Exception as exc:  # noqa: BLE001 - a transient network/exchange
            # hiccup must not crash a long-running live session.
            return PollResult(new_bars=0, error=f"{type(exc).__name__}: {exc}")
        if not new_bars:
            # a background autonomy step may have finished since last poll
            return PollResult(new_bars=0, autonomy_step=self._drain_completed_step())
        return PollResult(new_bars=len(new_bars), autonomy_step=self._process_new_bars(new_bars))

    def _process_new_bars(self, new_bars: list[MarketEvent]) -> AutonomyStepSummary | None:
        for cycle in self._universe.cycles(new_bars):
            self._process_cycle(cycle)
            self._bars_since_step += len(cycle.bars)

        # Persist + refresh the desk BEFORE scheduling autonomy work (perf
        # phase 3a) -- the UI shows fresh bars even while a step runs.
        self._persist_and_refresh()

        if self._bars_since_step >= self.config.autonomy_every:
            self._bars_since_step = 0
            self.step_count += 1
            if self._autonomy_pool is None:
                self._autonomy_pool = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="lqe-autonomy"
                )
            self._pending_steps.append(
                self._autonomy_pool.submit(
                    self._run_autonomy_step,
                    self.step_count,
                    new_bars[-1].ts_open,
                    list(self.bars_so_far),
                )
            )

        return self._drain_completed_step()

    def _run_autonomy_step(
        self, step_number: int, now: datetime, bars_snapshot: list[MarketEvent]
    ) -> AutonomyStepSummary:
        """One orchestrator step on the worker thread, over the bar snapshot
        captured when the step came due. `bars` is a public dataclass field;
        `_search_bars` mirrors exactly the slice `Orchestrator.__post_init__`
        itself computes from `bars`/`search_fraction` -- re-deriving it here
        (rather than re-running `__post_init__`, which would also reset its
        own engine and discard prior autonomy events) keeps that invariant
        intact. The orchestrator is only ever touched from this single
        worker (steps are FIFO on a one-thread pool), so per-step inputs and
        its audit chain match a synchronous run exactly."""
        self.orchestrator.bars = bars_snapshot
        cut = max(2, int(len(bars_snapshot) * self.orchestrator.search_fraction))
        self.orchestrator._search_bars = list(bars_snapshot[:cut])  # noqa: SLF001
        state = self.orchestrator.step(now=now)
        return AutonomyStepSummary(
            step_count=step_number, focus_model=state.focus_model,
            verdict=state.verdict, promoted=state.promoted, narration=state.narration,
        )

    def _drain_completed_step(self) -> AutonomyStepSummary | None:
        """Report the oldest finished background step, if any (one per poll,
        FIFO, so every step is surfaced in order). Also refreshes the desk
        so the step's autonomy events appear as soon as they exist."""
        if not self._pending_steps or not self._pending_steps[0].done():
            return None
        future = self._pending_steps.popleft()
        if future.cancelled():  # dropped by close() before it started
            return None
        summary = future.result()
        self.desk_data.set_state_reader(self._rebuild_state_reader())
        return summary

    def autonomy_running(self) -> bool:
        return bool(self._pending_steps) and not self._pending_steps[0].done()

    def close(self) -> None:
        """Let the in-flight autonomy step (if any) finish, drop queued
        not-yet-started ones, and stop the worker. Completed steps stay
        drainable. Safe to call more than once; sessions that never
        scheduled a step no-op."""
        if self._autonomy_pool is not None:
            self._autonomy_pool.shutdown(wait=True, cancel_futures=True)
            self._autonomy_pool = None

    def _persist_and_refresh(self) -> None:
        if self.config.out_path is not None:
            self._persisted = self.trade_engine.audit.append_jsonl(
                self.config.out_path, start=self._persisted
            )
        self.desk_data.set_state_reader(self._rebuild_state_reader())
