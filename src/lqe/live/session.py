"""`LiveSession` (docs/13 M18): the reusable core of `lqe live`, extracted
from `cli._cmd_live` so both the CLI and the new GUI-triggered job runner
(`ops/jobs.py`) share exactly one implementation rather than maintaining two.

Everything here is unchanged behavior from the pre-extraction `_cmd_live` --
same seed/resume logic (docs/12 M15), same fleet/engine/orchestrator wiring,
same write-through persistence to `--out`. Only the CLI-specific bits (print
statements, browser-opening, the blocking main loop) stay in `cli.py`/
`ops/jobs.py`, which each drive this class differently: the CLI loops
synchronously with its own prints; the job runner drives it from a
background thread and reports status to the desk instead of stdout.

Still paper-only end to end: `PaperBroker` is still the only
`ExecutionAdapter`, `make_order` is still the only `Order` constructor, and
one shared `KillSwitch` halts every model's new entries at once.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from lqe.data.base import MarketDataAdapter
from lqe.live.control import ControlPlane
from lqe.live.live_feed import LiveFeed
from lqe.live.merge import merged_records
from lqe.live.multi_model_runner import LiveMultiModelRunner, build_fleet
from lqe.models.catalog import ModelCatalog
from lqe.models.catalog_scale import build_scaled_catalog
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.data import CatalogRow, DeskData


def _market_events_from_audit(audit: AuditLog) -> list[MarketEvent]:
    # MarketEvents are emitted in processing order (one per bar) by
    # LiveMultiModelRunner.process_bar, so the audit's own seq order is
    # already the correct chronological order -- no re-sort needed.
    return [
        MarketEvent.model_validate(envelope.payload)
        for envelope in audit.records
        if envelope.type == "MarketEvent"
    ]


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
    symbol: Symbol
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
        self.feed = LiveFeed(
            adapter=adapter, symbol=config.symbol, timeframe=config.timeframe,
            poll_seconds=config.poll_seconds,
        )
        self.bars_so_far: list[MarketEvent] = []
        self.resumed = False
        self._bars_since_step = 0
        self.step_count = 0
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
        history: list[MarketEvent]
        if out_path is not None and out_path.exists():
            prior_audit = AuditLog.from_jsonl(out_path)
            history = _market_events_from_audit(prior_audit)
            self.resumed = True
            self.feed.resume_from(history)
        else:
            history = self.feed.seed_history(lookback_bars=self.config.lookback_bars)
        if not history:
            return False

        catalog, results = build_scaled_catalog(self.config.symbol)
        self.catalog = catalog
        self.catalog_results = results
        admitted = catalog.all()

        risk_model = RiskModel(kill_switch=self.kill_switch)
        fleet = build_fleet(admitted, starting_cash=self.config.starting_cash)
        self.trade_clock = ManualClock(history[0].ts_open)
        self.trade_engine = Engine(run_id="live-fleet", book="sandbox", clock=self.trade_clock)
        self.runner = LiveMultiModelRunner(
            engine=self.trade_engine, fleet=fleet, symbol=self.config.symbol, risk_model=risk_model
        )

        for bar in history:
            self.trade_clock.set(bar.ts_open)
            self.runner.process_bar(bar)
            self.bars_so_far.append(bar)
        if out_path is not None:
            self.trade_engine.audit.write_jsonl(out_path)

        self.orchestrator = Orchestrator(
            validator=Validator(),
            gate=PromotionGate(thresholds=GateThresholds(min_periods=self.config.min_periods)),
            optimizer=OptunaOptimizer(),
            searchable_models=broad_searchable_models(),
            bars=list(self.bars_so_far),
            symbol=self.config.symbol,
            starting_cash=self.config.starting_cash,
            run_id="live-fleet-autonomy",
            n_trials=self.config.n_trials,
            narrator=make_narrator(
                use_llm=self.config.use_llm, model=self.config.llm_model, seed=0, timeout_s=45.0
            ),
        )

        self._catalog_info = [
            # Every admitted model is author-declared "unproven" at intake
            # (models.manifest); only a gate PASS elsewhere ever sets "validated".
            CatalogModelInfo(
                model_id=e.manifest.id, family=e.manifest.family,
                sleeve=e.manifest.sleeve, status="unproven",
            )
            for e in admitted
        ]

        if self._desk_data is None:
            control = ControlPlane(kill_switch=self.kill_switch)
            self._desk_data = DeskData(
                state_reader=self._rebuild_state_reader(), control=control,
                catalog_rows=_catalog_rows(catalog),
            )
        else:
            self._desk_data.set_state_reader(self._rebuild_state_reader())
            self._desk_data.set_catalog_rows(_catalog_rows(catalog))
        return True

    def _rebuild_state_reader(self) -> StateReader:
        return StateReader(
            merged_records(self.trade_engine, self.orchestrator.engine), catalog=self._catalog_info
        )

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
            return PollResult(new_bars=0)
        return PollResult(new_bars=len(new_bars), autonomy_step=self._process_new_bars(new_bars))

    def _process_new_bars(self, new_bars: list[MarketEvent]) -> AutonomyStepSummary | None:
        for bar in new_bars:
            self.trade_clock.set(bar.ts_open)
            self.runner.process_bar(bar)
            self.bars_so_far.append(bar)
            self._bars_since_step += 1

        # Grow the orchestrator's data window as history accumulates. `bars`
        # is a public dataclass field; `_search_bars` mirrors exactly the
        # slice `Orchestrator.__post_init__` itself computes from
        # `bars`/`search_fraction` -- re-deriving it here (rather than
        # re-running `__post_init__`, which would also reset its own engine
        # and discard prior autonomy events) keeps that invariant intact.
        self.orchestrator.bars = list(self.bars_so_far)
        cut = max(2, int(len(self.orchestrator.bars) * self.orchestrator.search_fraction))
        self.orchestrator._search_bars = list(self.orchestrator.bars[:cut])  # noqa: SLF001

        summary: AutonomyStepSummary | None = None
        if self._bars_since_step >= self.config.autonomy_every:
            self._bars_since_step = 0
            self.step_count += 1
            state = self.orchestrator.step(now=new_bars[-1].ts_open)
            summary = AutonomyStepSummary(
                step_count=self.step_count, focus_model=state.focus_model,
                verdict=state.verdict, promoted=state.promoted, narration=state.narration,
            )

        if self.config.out_path is not None:
            self.trade_engine.audit.write_jsonl(self.config.out_path)
        self.desk_data.set_state_reader(self._rebuild_state_reader())
        return summary
