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

from typing import Literal

from pydantic import BaseModel, ConfigDict

from lqe.live.control import Command, ControlPlane
from lqe.storage.state_reader import StateReader, TapeRow, UIState

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
    ) -> None:
        self._state_reader = state_reader
        self._control = control
        self._catalog_rows = catalog_rows or []
        self._experiment_rows = experiment_rows or []
        self._daily_rows = daily_rows or []

    def snapshot(self) -> UIState:
        return self._state_reader.snapshot()

    def tape(self, *, after_seq: int = 0, limit: int = 200) -> list[TapeRow]:
        return self._state_reader.tape(after_seq=after_seq, limit=limit)

    def catalog(self) -> list[CatalogRow]:
        return list(self._catalog_rows)

    def experiments(self) -> list[ExperimentRow]:
        return list(self._experiment_rows)

    def daily(self) -> list[DailyRow]:
        return list(self._daily_rows)

    @property
    def kill_active(self) -> bool:
        return self._control.kill_active

    def submit_control(
        self, command: Command, *, source: str, operator: str, note: str = ""
    ) -> None:
        self._control.submit(command, source=source, operator=operator, note=note)

    def clear_kill(self, *, operator: str) -> None:
        self._control.clear_kill(operator=operator)
