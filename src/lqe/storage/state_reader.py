"""`StateReader` (docs/11 §11.2/§11.9): the read-only view the UI and 3D
space build from. It reconstructs a `UIState` and a structured event
`Tape` purely by replaying an audit log — it never reaches into the
engine, risk, or execution internals, and it constructs no `Order`. The
only writes in the whole UI path go through `live.control`, never here.

`storage/` depends on `core/` only (docs/11 §11.1), so catalog metadata
(family/status per model) is passed in as plain `CatalogModelInfo` data by
the caller rather than importing `models/` here — keeping the boundary
clean.

Honesty (docs/05 §5.3, docs/11 §11.9): `simulated` is always `True`,
every model cell carries its `n_trades` sample size and `unproven`/
`validated` status, and nothing here is ever framed as profit.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from lqe.core.engine import AuditLog
from lqe.core.events import EventEnvelope
from lqe.core.types import Symbol

_FROZEN = ConfigDict(frozen=True)

ModelState = Literal["ARMED", "LONG", "SHORT", "FIRED", "HALTED"]
ModelStatus = Literal["unproven", "validated"]


class CatalogModelInfo(BaseModel):
    """The slice of a model's manifest the floor needs, handed in by the
    caller so `storage/` need not import `models/`."""

    model_config = _FROZEN
    model_id: str
    family: str
    status: ModelStatus = "unproven"


class ModelCell(BaseModel):
    model_config = _FROZEN
    model_id: str
    family: str
    state: ModelState
    status: ModelStatus
    sim_return_pct: float | None  # None = not enough data yet (rendered "—")
    n_trades: int
    last_reason: str


class SessionStats(BaseModel):
    model_config = _FROZEN
    equity: Decimal
    pnl_pct: float
    exposure: float
    drawdown: float


class DataHealth(BaseModel):
    model_config = _FROZEN
    symbol: Symbol
    last_bar: datetime | None
    bars_seen: int


class UIState(BaseModel):
    """docs/11 §11.9. `simulated` is a hard-coded honesty flag, never a
    field a run can flip off."""

    model_config = _FROZEN
    run_id: str
    simulated: Literal[True] = True
    kill_active: bool
    breaches: list[str]
    session: SessionStats | None
    models: list[ModelCell]
    data_health: list[DataHealth]


class TapeRow(BaseModel):
    """One designed row per audit event (docs/05 §5.3) — structured, never
    a console line."""

    model_config = _FROZEN
    seq: int
    sim_ts: datetime
    type: str
    summary: str
    detail: str


class DecisionCard(BaseModel):
    """One autonomy step rendered as a card (docs/05 §5.4, docs/10 M9):
    hypothesis → search → validate → promote/kill. Reconstructed read-only
    from the audit's autonomy events."""

    model_config = _FROZEN
    hypo_id: str
    model_id: str
    rationale: str
    degradation_triggered: bool
    n_trials: int
    verdict: Literal["PASS", "FAIL", "PENDING"]
    dsr: float | None
    pbo: float | None
    promoted: bool
    llm_used: bool
    narration: str


class StateReader:
    def __init__(
        self,
        records: list[EventEnvelope],
        *,
        catalog: list[CatalogModelInfo] | None = None,
    ) -> None:
        self._records = records
        self._catalog = {c.model_id: c for c in (catalog or [])}
        self._run_id = records[0].run_id if records else ""

    @classmethod
    def from_jsonl(
        cls, path: Path, *, catalog: list[CatalogModelInfo] | None = None
    ) -> StateReader:
        audit = AuditLog.from_jsonl(path)
        return cls(audit.records, catalog=catalog)

    @classmethod
    def from_audit(
        cls, audit: AuditLog, *, catalog: list[CatalogModelInfo] | None = None
    ) -> StateReader:
        return cls(audit.records, catalog=catalog)

    # -- snapshot ---------------------------------------------------------

    def snapshot(self) -> UIState:
        recon = _Reconstruction(self._records, self._catalog)
        return UIState(
            run_id=self._run_id,
            kill_active=recon.kill_active,
            breaches=recon.breaches,
            session=recon.session(),
            models=recon.model_cells(),
            data_health=recon.data_health(),
        )

    # -- tape -------------------------------------------------------------

    def tape(self, *, after_seq: int = 0, limit: int = 200) -> list[TapeRow]:
        """Structured event rows with `seq > after_seq` (so the UI can poll
        incrementally), most-recent last, capped at `limit`."""
        rows = [_tape_row(env) for env in self._records if env.seq > after_seq]
        return rows[-limit:]

    # -- decision cards ---------------------------------------------------

    def decision_cards(self, *, limit: int = 30) -> list[DecisionCard]:
        """The autonomy loop's steps as cards, newest first (docs/10 M9). A
        `HypothesisEvent` opens a card; the events emitted after it (trials,
        validation, promotion, narration, LLM calls) up to the next
        hypothesis belong to it. A preceding `DeRiskEvent` marks the card as
        degradation-triggered."""
        cards: list[_CardBuilder] = []
        pending_derisk = False
        for env in self._records:
            t = env.type
            if t == "DeRiskEvent":
                pending_derisk = True
                continue
            if t == "HypothesisEvent":
                p = env.payload
                models = p.get("target_models") or []
                cards.append(
                    _CardBuilder(
                        hypo_id=str(p["hypo_id"]),
                        model_id=str(models[0]) if models else "?",
                        rationale=str(p.get("rationale", "")),
                        degradation_triggered=pending_derisk,
                    )
                )
                pending_derisk = False
            elif cards:
                cards[-1].absorb(t, env.payload)
        built = [c.build() for c in cards]
        return list(reversed(built))[:limit]


# --- decision-card assembly -----------------------------------------------


class _CardBuilder:
    def __init__(
        self, *, hypo_id: str, model_id: str, rationale: str, degradation_triggered: bool
    ) -> None:
        self.hypo_id = hypo_id
        self.model_id = model_id
        self.rationale = rationale
        self.degradation_triggered = degradation_triggered
        self.n_trials = 0
        self.verdict: Literal["PASS", "FAIL", "PENDING"] = "PENDING"
        self.dsr: float | None = None
        self.pbo: float | None = None
        self.promoted = False
        self.llm_used = False
        self.narration = ""

    def absorb(self, event_type: str, payload: dict[str, object]) -> None:
        if event_type == "TrialEvent":
            self.n_trials += 1
        elif event_type == "ValidationEvent":
            self.verdict = "PASS" if payload.get("result") == "PASS" else "FAIL"
            self.dsr = float(str(payload.get("dsr", "nan")))
            self.pbo = float(str(payload.get("pbo", "nan")))
        elif event_type == "PromotionEvent":
            self.promoted = True
        elif event_type == "LlmCallEvent":
            self.llm_used = True
        elif event_type == "NarrationEvent":
            self.narration = str(payload.get("text", ""))

    def build(self) -> DecisionCard:
        return DecisionCard(
            hypo_id=self.hypo_id,
            model_id=self.model_id,
            rationale=self.rationale,
            degradation_triggered=self.degradation_triggered,
            n_trials=self.n_trials,
            verdict=self.verdict,
            dsr=self.dsr,
            pbo=self.pbo,
            promoted=self.promoted,
            llm_used=self.llm_used,
            narration=self.narration,
        )


# --- reconstruction -------------------------------------------------------


class _StrategyAgg:
    def __init__(self) -> None:
        self.net_qty = Decimal("0")
        self.n_trades = 0
        self.realized = Decimal("0")
        self.last_reason = ""
        self.last_direction = "FLAT"
        self.fired_on_last_seq = False
        self._lots: list[tuple[Decimal, Decimal]] = []  # (qty, px) FIFO, long-only round trips

    def on_buy(self, qty: Decimal, px: Decimal, fee: Decimal) -> None:
        self._lots.append((qty, px))
        self.net_qty += qty
        self.realized -= fee
        self.n_trades += 1

    def on_sell(self, qty: Decimal, px: Decimal, fee: Decimal) -> None:
        remaining = qty
        while remaining > 0 and self._lots:
            lot_qty, lot_px = self._lots[0]
            matched = min(remaining, lot_qty)
            self.realized += matched * (px - lot_px)
            remaining -= matched
            if matched >= lot_qty:
                self._lots.pop(0)
            else:
                self._lots[0] = (lot_qty - matched, lot_px)
        self.net_qty -= qty
        self.realized -= fee
        self.n_trades += 1


class _Reconstruction:
    def __init__(self, records: list[EventEnvelope], catalog: dict[str, CatalogModelInfo]) -> None:
        self._records = records
        self._catalog = catalog
        self._max_seq = records[-1].seq if records else 0

        self._order_to_strategy: dict[str, str] = {}
        self._order_to_side: dict[str, str] = {}
        self._intent_to_strategy: dict[str, str] = {}
        self._strategies: dict[str, _StrategyAgg] = defaultdict(_StrategyAgg)
        self._last_risk_state: dict[str, object] | None = None
        self._starting_equity: Decimal | None = None
        self._symbols: dict[Symbol, tuple[datetime | None, int]] = {}
        self.kill_active = False
        self.breaches: list[str] = []

        self._walk()

    def _walk(self) -> None:
        for env in self._records:
            handler = getattr(self, f"_on_{env.type}", None)
            if handler is not None:
                handler(env)

    def _on_MarketEvent(self, env: EventEnvelope) -> None:
        p = env.payload
        sym = str(p["symbol"])
        last_ts, seen = self._symbols.get(sym, (None, 0))
        ts = datetime.fromisoformat(str(p["ts_open"]))
        self._symbols[sym] = (ts, seen + 1)

    def _on_SignalEvent(self, env: EventEnvelope) -> None:
        p = env.payload
        agg = self._strategies[str(p["strategy"])]
        agg.last_reason = str(p.get("reason", ""))
        agg.last_direction = str(p["direction"])

    def _on_OrderIntent(self, env: EventEnvelope) -> None:
        p = env.payload
        self._intent_to_strategy[str(p["intent_id"])] = str(p["strategy"])

    def _on_Order(self, env: EventEnvelope) -> None:
        p = env.payload
        order_id = str(p["order_id"])
        intent_ref = str(p["intent_ref"])
        strategy = self._intent_to_strategy.get(intent_ref)
        if strategy is not None:
            self._order_to_strategy[order_id] = strategy
        self._order_to_side[order_id] = str(p["side"])

    def _on_FillEvent(self, env: EventEnvelope) -> None:
        p = env.payload
        order_id = str(p["order_id"])
        strategy = self._order_to_strategy.get(order_id)
        if strategy is None:
            return
        agg = self._strategies[strategy]
        qty = Decimal(str(p["fill_qty"]))
        px = Decimal(str(p["fill_px"]))
        fee = Decimal(str(p["fee"]))
        side = self._order_to_side.get(order_id, "BUY")
        if side == "BUY":
            agg.on_buy(qty, px, fee)
        else:
            agg.on_sell(qty, px, fee)
        agg.fired_on_last_seq = env.seq == self._max_seq

    def _on_RiskStateEvent(self, env: EventEnvelope) -> None:
        p = env.payload
        self._last_risk_state = dict(p)
        if self._starting_equity is None:
            self._starting_equity = Decimal(str(p["equity"]))
        self.kill_active = bool(p.get("kill_active", False))
        self.breaches = [str(b) for b in p.get("breaches", [])]

    # -- outputs ----------------------------------------------------------

    def session(self) -> SessionStats | None:
        if self._last_risk_state is None:
            return None
        p = self._last_risk_state
        equity = Decimal(str(p["equity"]))
        start = self._starting_equity or equity
        pnl_pct = float((equity - start) / start * 100) if start > 0 else 0.0
        gross = Decimal(str(p["gross_exposure"]))
        exposure = float(gross / equity) if equity > 0 else 0.0
        return SessionStats(
            equity=equity,
            pnl_pct=pnl_pct,
            exposure=exposure,
            drawdown=float(str(p["drawdown"])),
        )

    def model_cells(self) -> list[ModelCell]:
        # union of catalog models and any strategy that actually traded
        ids = list(self._catalog) + [s for s in self._strategies if s not in self._catalog]
        cells = []
        for model_id in ids:
            info = self._catalog.get(model_id)
            agg = self._strategies.get(model_id)
            family = info.family if info else "unknown"
            status: ModelStatus = info.status if info else "unproven"
            state = _model_state(agg, kill_active=self.kill_active)
            sim_return = _sim_return_pct(agg, self._starting_equity)
            cells.append(
                ModelCell(
                    model_id=model_id,
                    family=family,
                    state=state,
                    status=status,
                    sim_return_pct=sim_return,
                    n_trades=agg.n_trades if agg else 0,
                    last_reason=agg.last_reason if agg else "",
                )
            )
        return cells

    def data_health(self) -> list[DataHealth]:
        return [
            DataHealth(symbol=sym, last_bar=last, bars_seen=seen)
            for sym, (last, seen) in sorted(self._symbols.items())
        ]


def _model_state(agg: _StrategyAgg | None, *, kill_active: bool) -> ModelState:
    if kill_active:
        return "HALTED"
    if agg is None or agg.net_qty == 0:
        return "ARMED"
    if agg.fired_on_last_seq:
        return "FIRED"
    return "LONG" if agg.net_qty > 0 else "SHORT"


def _sim_return_pct(agg: _StrategyAgg | None, starting_equity: Decimal | None) -> float | None:
    if agg is None or agg.n_trades == 0 or starting_equity is None or starting_equity <= 0:
        return None
    return float(agg.realized / starting_equity * 100)


# --- tape formatting ------------------------------------------------------


def _tape_row(env: EventEnvelope) -> TapeRow:
    summary, detail = _describe(env)
    return TapeRow(seq=env.seq, sim_ts=env.sim_ts, type=env.type, summary=summary, detail=detail)


def _describe(env: EventEnvelope) -> tuple[str, str]:
    p = env.payload
    t = env.type
    if t == "SignalEvent":
        return f"{p['strategy']} {p['direction']}", str(p.get("reason", ""))
    if t == "OrderIntent":
        return f"{p['strategy']} {p['side']} {p['qty']}", str(p.get("reason", ""))
    if t == "RiskDecision":
        hits = ", ".join(str(h) for h in p.get("rule_hits", []))
        return f"risk: {p['verdict']}", hits
    if t == "Order":
        return f"order {p['side']} {p['qty']}", f"status {p['status']}"
    if t == "FillEvent":
        return f"fill {p['fill_qty']} @ {p['fill_px']} (sim)", f"fee {p['fee']}"
    if t == "RiskStateEvent":
        return f"equity {p['equity']} (sim)", f"dd {p['drawdown']}"
    if t == "ControlEvent":
        return f"{p['command']}", f"{p.get('source', '')}: {p.get('note', '')}"
    if t == "MarketEvent":
        return f"{p['symbol']} bar", f"c={p['c']}"
    return t, ""
