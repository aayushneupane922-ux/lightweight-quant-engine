"""View-model types + the injectable `DeskData` the UI renders from
(docs/05 §5.6). Everything the templates show is assembled here from a
read-only `StateReader` plus plain rows the caller supplies — the UI layer
imports `storage.state_reader` and `live.control` only, never `models`,
`risk`, `execution`, or `autonomy` internals (docs/11 §11.1).

The honesty layer (docs/05 §5.3) lives in these types: every model/
experiment row carries its sample size and `unproven`/`validated` status,
and `simulated` is always true on the snapshot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from lqe.live.control import Command, ControlPlane
from lqe.storage.state_reader import (
    BlotterRow,
    ConversationPayload,
    DecisionCard,
    EquityPoint,
    GraphPayload,
    PriceBar,
    ReconciliationRow,
    StateReader,
    TapeRow,
    UIState,
    blotter_empty_state_reason,
)

if TYPE_CHECKING:
    # docs/13 M18: the GUI job-trigger surface. Only imported for the type
    # hint below -- `ops.jobs` isn't in the ui-boundary test's forbidden
    # list (risk/execution/autonomy/models), so a real (non-TYPE_CHECKING)
    # import would also be allowed, but this keeps the module import-light
    # for callers that never construct a JobManager (e.g. `lqe desk`).
    from lqe.ops.jobs import JobManager

_FROZEN = ConfigDict(frozen=True)


class CatalogRow(BaseModel):
    """A model as the Catalog view browses it (docs/03 §3.5) — manifest
    facts only, plus its honest status. Never rendered as validated unless
    a gate PASS set it."""

    model_config = _FROZEN
    model_id: str
    family: str
    one_liner: str
    oss_libs: list[str]
    status: Literal["unproven", "in_research", "validated"]
    quarantined: bool = False
    quarantine_reason: str = ""


class ExperimentRow(BaseModel):
    """One Research/gate row (docs/11 §11.4 experiments) with its evidence
    and sample size front and centre."""

    model_config = _FROZEN
    run_id: str
    strategy: str
    sharpe: float
    dsr: float
    pbo: float
    max_dd: float
    n_trades: int
    cost_bps: float
    passed_gate: bool


class DailyRow(BaseModel):
    """One session's daily report (docs/11 §11.4 daily_reports)."""

    model_config = _FROZEN
    session_date: str
    start_equity: float
    end_equity: float
    pnl: float
    n_trades: int
    max_intraday_dd: float
    reconciled: bool


class DeskData:
    """Bundles the read side (`StateReader`) and the reference rows the
    non-live views need. The write side is `control` — the *only* mutating
    path the UI can reach."""

    def __init__(
        self,
        *,
        state_reader: StateReader,
        control: ControlPlane,
        catalog_rows: list[CatalogRow] | None = None,
        experiment_rows: list[ExperimentRow] | None = None,
        daily_rows: list[DailyRow] | None = None,
        jobs: JobManager | None = None,
    ) -> None:
        self._state_reader = state_reader
        self._control = control
        self._catalog_rows = catalog_rows or []
        self._experiment_rows = experiment_rows or []
        self._daily_rows = daily_rows or []
        # docs/13 M18: optional GUI job-trigger surface (ingest/backtest/
        # live start-stop). None for `lqe desk`'s read-only render path,
        # which never needs it.
        self.jobs = jobs

    def set_catalog_rows(self, catalog_rows: list[CatalogRow]) -> None:
        """Swap the Catalog view's rows (docs/13 M18: a GUI-started live
        session rebuilds the catalog once at setup and hands it here) --
        same atomic-attribute-swap reasoning as `set_state_reader`."""
        self._catalog_rows = catalog_rows

    def set_state_reader(self, state_reader: StateReader) -> None:
        """Swap the read-side snapshot (post-v1.0 live-refresh extension): a
        live-polling loop can periodically replace this with a `StateReader`
        rebuilt from the current, growing audit log, so the desk visibly
        updates as new events arrive without a restart. A plain attribute
        swap is atomic under the GIL for this single-writer/many-readers
        pattern (one background thread writes, request handlers only read)
        -- no lock needed, and every existing read method already re-derives
        from `self._state_reader` on each call rather than caching."""
        self._state_reader = state_reader

    def snapshot(self) -> UIState:
        return self._state_reader.snapshot()

    def tape(self, *, after_seq: int = 0, limit: int = 200) -> list[TapeRow]:
        return self._state_reader.tape(after_seq=after_seq, limit=limit)

    def decision_cards(self, *, limit: int = 30) -> list[DecisionCard]:
        return self._state_reader.decision_cards(limit=limit)

    def conversation(self, *, at_seq: int | None = None) -> ConversationPayload:
        return self._state_reader.conversation(at_seq=at_seq)

    def graph(self, *, at_seq: int | None = None) -> GraphPayload:
        return self._state_reader.graph(at_seq=at_seq)

    def price_series(self, symbol: str, *, max_points: int = 1000) -> list[PriceBar]:
        return self._state_reader.price_series(symbol, max_points=max_points)

    def equity_curve(self, *, max_points: int = 1000) -> list[EquityPoint]:
        return self._state_reader.equity_curve(max_points=max_points)

    def blotter(self, *, after_seq: int = 0, limit: int = 500) -> list[BlotterRow]:
        return self._state_reader.blotter(after_seq=after_seq, limit=limit)

    def reconciliation(self) -> list[ReconciliationRow]:
        return self._state_reader.reconciliation()

    def blotter_empty_state(self) -> str | None:
        return blotter_empty_state_reason(self._state_reader.snapshot(), self.blotter())

    def catalog(self) -> list[CatalogRow]:
        return list(self._catalog_rows)

    def experiments(self) -> list[ExperimentRow]:
        return list(self._experiment_rows)

    def daily(self) -> list[DailyRow]:
        return list(self._daily_rows)

    @property
    def kill_active(self) -> bool:
        return self._control.kill_active

    @property
    def autopilot_on(self) -> bool:
        return self._control.autopilot_on

    def submit_control(
        self, command: Command, *, source: str, operator: str, note: str = ""
    ) -> None:
        self._control.submit(command, source=source, operator=operator, note=note)

    def clear_kill(self, *, operator: str) -> None:
        self._control.clear_kill(operator=operator)
