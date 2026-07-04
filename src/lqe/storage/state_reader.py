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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lqe.core.engine import AuditLog
from lqe.core.events import EventEnvelope
from lqe.core.types import Symbol

_FROZEN = ConfigDict(frozen=True)

ModelState = Literal["ARMED", "LONG", "SHORT", "FIRED", "HALTED"]
ModelStatus = Literal["unproven", "validated"]

# V5 M26 "living model cells": the floor's per-cell sparkline is a bounded
# ring of the last N `sim_return_pct` samples (one per fill) -- capped the
# same way ADAPTER_HISTORY_CAP bounds adapter history, so a long-running
# session's memory/serialization cost per cell stays flat.
_SPARKLINE_CAP = 24


class CatalogModelInfo(BaseModel):
    """The slice of a model's manifest the floor needs, handed in by the
    caller so `storage/` need not import `models/`."""

    model_config = _FROZEN
    model_id: str
    family: str
    # docs/14 (v4): the return-driver sleeve -- the catalog's actual
    # diversification unit, coarser than `family`. Defaulted so pre-v4
    # direct constructions (tests) don't need updating.
    sleeve: str = "—"
    status: ModelStatus = "unproven"


class ModelCell(BaseModel):
    model_config = _FROZEN
    model_id: str
    family: str
    sleeve: str = "—"
    state: ModelState
    status: ModelStatus
    sim_return_pct: float | None  # None = not enough data yet (rendered "—")
    n_trades: int
    last_reason: str
    # V5 M26 living cells: last <=24 sim_return_pct samples, oldest first
    # (one per fill); and how much of current equity this model's open
    # position represents, in [0, 1] -- long-only, so never bidirectional.
    sparkline_pct: list[float] = []
    stance_pct: float = 0.0


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


class PriceBar(BaseModel):
    """One OHLCV bar for the Floor hero chart (docs/13 M19) — read straight
    off `MarketEvent`s already in the audit log, no new event type."""

    model_config = _FROZEN
    ts: datetime
    o: Decimal
    h: Decimal
    l: Decimal  # noqa: E741 — matches MarketEvent's wire field name
    c: Decimal
    v: float


class EquityPoint(BaseModel):
    """One point of the equity curve (docs/13 M19) — read straight off
    `RiskStateEvent`s already in the audit log, no new event type."""

    model_config = _FROZEN
    ts: datetime
    equity: Decimal


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


class BlotterRow(BaseModel):
    """One row of the live trade blotter (docs/13 M20): a signal's full
    order lifecycle -- intent -> risk decision -> fill/reject -- read
    straight off `OrderIntent`/`RiskDecision`/`FillEvent` already in the
    audit log. One row per fill; a `REJECT`ed (or approved-but-not-yet-
    filled) intent gets exactly one row with no fill fields, so nothing
    silently vanishes."""

    model_config = _FROZEN
    seq: int
    sim_ts: datetime
    model: str
    symbol: Symbol
    side: Literal["BUY", "SELL"]
    intent_qty: Decimal
    reason: str
    verdict: Literal["APPROVE", "CLAMP", "REJECT"]
    rule_hits: list[str]
    fill_qty: Decimal | None
    fill_px: Decimal | None
    fee: Decimal | None
    slippage_bps: float | None
    partial: bool
    sim_pnl: Decimal | None  # this fill's own realized-P&L delta; None if no fill


class ReconciliationRow(BaseModel):
    """Per-model position/P&L, tied out to the audit log (docs/13 M20
    "standard blotter practice"). `net_qty`/`realized_pnl` come from the
    same FIFO lot accounting `model_cells()` uses -- not a second,
    divergent computation."""

    model_config = _FROZEN
    model_id: str
    net_qty: Decimal
    realized_pnl: Decimal
    n_trades: int


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


Participant = Literal["Strategist", "Optimizer", "Judge", "Autopilot", "Risk"]


class ConversationMessage(BaseModel):
    """One turn of the "Engine Room" conversation (docs/13 M21): the LLM
    (Strategist), Optuna (Optimizer), the Validator (Judge), Autopilot, and
    Risk, rendered as a readable dialogue -- reconstructed read-only from
    the same autonomy/narration/control events `decision_cards()` reads,
    just as individual turns instead of one summary card per hypothesis.
    `detail` is plain text (never raw JSON) for an optional "Details"
    disclosure; `verdict` is set only on the Judge's validation card, so
    the UI can color it long/short by outcome rather than a fixed hue."""

    model_config = _FROZEN
    seq: int
    sim_ts: datetime
    participant: Participant
    kind: Literal["message", "card"]
    text: str
    detail: str = ""
    model_id: str = ""
    verdict: Literal["PASS", "FAIL"] | None = None


class ConversationPayload(BaseModel):
    """docs/13 M21. `at_seq`/`max_seq` support the same replay-at-a-point
    pattern as `GraphPayload` -- because runs are deterministic, scrubbing
    to an earlier `at_seq` reproduces that exact prefix of the
    conversation, every time."""

    model_config = _FROZEN
    at_seq: int
    max_seq: int
    messages: list[ConversationMessage]


NodeKind = Literal["tracked", "sandbox", "meta", "regime"]
LinkKind = Literal["corr+", "corr-", "dataflow", "attention", "promotion"]


class GraphNode(BaseModel):
    """One node of the 3D neural-web (docs/11 §11.9). Honesty fields
    (`n_trades`, `status`) are always present; a rising tracked core reads
    as `validated`, a churning sandbox as `unproven`."""

    model_config = _FROZEN
    id: str
    label: str
    family: str
    kind: NodeKind
    state: ModelState
    conviction: float  # 0..1, a display heuristic (attention/evidence), never P&L
    sim_return: float
    n_trades: int
    status: ModelStatus


class GraphLink(BaseModel):
    model_config = _FROZEN
    source: str
    target: str
    kind: LinkKind
    weight: float  # 0..1


class GraphPayload(BaseModel):
    """docs/11 §11.9. Read-only; `simulated` is a hard-coded honesty flag."""

    model_config = _FROZEN
    run_id: str
    simulated: Literal[True] = True
    at_seq: int
    max_seq: int
    nodes: list[GraphNode]
    links: list[GraphLink]
    regions: dict[str, list[str]]  # {"tracked": [...ids], "sandbox": [...ids]}


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
        # A reader's record list is fixed at construction, so every derived
        # view is computed at most once per instance. Without this, the
        # desk's 2s WebSocket frame replayed the ENTIRE audit log 3x per
        # frame (snapshot + tape + blotter) and hours-long live sessions got
        # progressively slower. A first-call race between uvicorn threadpool
        # threads is benign -- both compute identical results and attribute
        # assignment is atomic -- so no lock.
        self._recon_cache: _Reconstruction | None = None
        self._snapshot_cache: UIState | None = None
        self._blotter_cache: list[BlotterRow] | None = None
        self._price_cache: dict[Symbol, list[PriceBar]] = {}
        self._equity_cache: list[EquityPoint] | None = None

    def _reconstruction(self) -> _Reconstruction:
        if self._recon_cache is None:
            self._recon_cache = _Reconstruction(self._records, self._catalog)
        return self._recon_cache

    @property
    def max_seq(self) -> int:
        return self._records[-1].seq if self._records else 0

    def extended(self, new_records: list[EventEnvelope]) -> StateReader:
        """A NEW reader over this one's records + `new_records`, carrying
        the already-built reconstruction and chart caches forward so only
        the tail is walked (perf phase 2b) -- the live loop calls this once
        per poll instead of paying a full-log replay as sessions grow. This
        reader is never mutated, so in-flight readers on other threads (the
        desk's request handlers) stay consistent; the caller swaps the new
        reader in atomically via `DeskData.set_state_reader`, as before.

        Only valid when `new_records` extend this reader's view append-only
        (same prefix, strictly later records) -- the live loop's
        `IncrementalMerge` guarantees that and falls back to a fresh
        `StateReader` construction whenever it can't."""
        reader = StateReader(self._records + new_records)
        reader._catalog = self._catalog  # read-only mapping, safe to share
        reader._run_id = self._run_id or (new_records[0].run_id if new_records else "")
        if self._recon_cache is not None:
            reader._recon_cache = self._recon_cache.extended(new_records, reader._records)
        for sym, bars in self._price_cache.items():
            reader._price_cache[sym] = bars + [
                _price_bar(env)
                for env in new_records
                if env.type == "MarketEvent" and str(env.payload["symbol"]) == sym
            ]
        if self._equity_cache is not None:
            reader._equity_cache = self._equity_cache + [
                _equity_point(env) for env in new_records if env.type == "RiskStateEvent"
            ]
        return reader

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
        if self._snapshot_cache is None:
            recon = self._reconstruction()
            self._snapshot_cache = UIState(
                run_id=self._run_id,
                kill_active=recon.kill_active,
                breaches=recon.breaches,
                session=recon.session(),
                models=recon.model_cells(),
                data_health=recon.data_health(),
            )
        return self._snapshot_cache

    # -- blotter (docs/13 M20) ---------------------------------------------

    def blotter(self, *, after_seq: int = 0, limit: int = 500) -> list[BlotterRow]:
        """The full order lifecycle (docs/13 M20), rows with `seq >
        after_seq`, oldest first, capped at `limit` -- same incremental-
        poll shape as `tape()`."""
        if self._blotter_cache is None:
            self._blotter_cache = self._reconstruction().blotter()
        rows = [r for r in self._blotter_cache if r.seq > after_seq]
        return rows[-limit:]

    def reconciliation(self) -> list[ReconciliationRow]:
        return self._reconstruction().reconciliation()

    # -- tape -------------------------------------------------------------

    def tape(self, *, after_seq: int = 0, limit: int = 200) -> list[TapeRow]:
        """Structured event rows with `seq > after_seq` (so the UI can poll
        incrementally), most-recent last, capped at `limit`.

        Scans backwards from the tail: the desk polls with `after_seq` near
        the head and a small `limit`, so this is O(limit) per call instead
        of a full-log walk. Records are seq-ascending, so collecting from
        the end while `seq > after_seq` (capped at `limit`) selects exactly
        the same rows as the naive full filter."""
        tail: list[EventEnvelope] = []
        for env in reversed(self._records):
            if env.seq <= after_seq:
                break
            tail.append(env)
            if len(tail) == limit:
                break
        return [_tape_row(env) for env in reversed(tail)]

    # -- charts (docs/13 M19) ----------------------------------------------

    def price_series(self, symbol: Symbol, *, max_points: int = 1000) -> list[PriceBar]:
        """OHLCV bars for `symbol`, oldest first, straight off `MarketEvent`s
        already in the audit log — no new event type. Downsampled to at
        most `max_points` (evenly-strided) so a long-running feed still
        renders a responsive chart."""
        if symbol not in self._price_cache:
            self._price_cache[symbol] = [
                _price_bar(env)
                for env in self._records
                if env.type == "MarketEvent" and str(env.payload["symbol"]) == symbol
            ]
        return _downsample(self._price_cache[symbol], max_points)

    def equity_curve(self, *, max_points: int = 1000) -> list[EquityPoint]:
        """The equity curve, oldest first, straight off `RiskStateEvent`s
        already in the audit log — no new event type. Downsampled to at
        most `max_points`."""
        if self._equity_cache is None:
            self._equity_cache = [
                _equity_point(env) for env in self._records if env.type == "RiskStateEvent"
            ]
        return _downsample(self._equity_cache, max_points)

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

    # -- "Engine Room" conversation (docs/13 M21) ---------------------------

    def conversation(self, *, at_seq: int | None = None) -> ConversationPayload:
        """The autonomy loop as a readable dialogue, oldest first --
        reconstructed straight from `HypothesisEvent`/`TrialEvent`/
        `ValidationEvent`/`PromotionEvent`/`DeRiskEvent`/`NarrationEvent`/
        `ControlEvent`, exactly the events `decision_cards()` already reads,
        just presented as turns instead of one card per hypothesis.
        `at_seq` replays the conversation exactly as it was at that point in
        the session (same deterministic-replay pattern as `graph()`)."""
        max_seq = self._records[-1].seq if self._records else 0
        effective = max_seq if at_seq is None else at_seq
        records = [r for r in self._records if r.seq <= effective]

        messages: list[ConversationMessage] = []
        pending_trials: list[dict[str, Any]] = []
        pending_model = ""

        def flush_trials(anchor: EventEnvelope) -> None:
            if not pending_trials:
                return
            best = max(pending_trials, key=lambda t: float(t["oos_metric"]))
            params = ", ".join(f"{k}={v}" for k, v in best["params"].items())
            text = f"Ran {len(pending_trials)} trials — best Sharpe {best['oos_metric']:.2f}"
            if params:
                text += f" ({params})"
            messages.append(
                ConversationMessage(
                    seq=anchor.seq, sim_ts=anchor.sim_ts, participant="Optimizer", kind="card",
                    text=text, model_id=pending_model,
                )
            )
            pending_trials.clear()

        for env in records:
            t = env.type
            p = env.payload
            if t == "HypothesisEvent":
                flush_trials(env)
                models = p.get("target_models") or []
                pending_model = str(models[0]) if models else ""
                messages.append(
                    ConversationMessage(
                        seq=env.seq, sim_ts=env.sim_ts, participant="Strategist", kind="message",
                        text=str(p.get("rationale", "")), model_id=pending_model,
                    )
                )
            elif t == "TrialEvent":
                pending_trials.append(
                    {"oos_metric": float(p["oos_metric"]), "params": dict(p.get("params") or {})}
                )
            elif t == "ValidationEvent":
                flush_trials(env)
                messages.append(_validation_message(env, pending_model))
            elif t == "PromotionEvent":
                model_id = _model_from_candidate(str(p.get("candidate_id", ""))) or pending_model
                messages.append(
                    ConversationMessage(
                        seq=env.seq, sim_ts=env.sim_ts, participant="Judge", kind="message",
                        text=f"Promoted {model_id or 'the candidate'} to the tracked book "
                        "— validated.",
                        model_id=model_id,
                    )
                )
            elif t == "DeRiskEvent":
                models_str = ", ".join(str(m) for m in (p.get("models") or []))
                messages.append(
                    ConversationMessage(
                        seq=env.seq, sim_ts=env.sim_ts, participant="Risk", kind="card",
                        text=f"De-risking {models_str or 'affected models'} "
                        f"({p.get('action', 'REDUCE')}) — {p.get('reason', '')}",
                        model_id=models_str,
                    )
                )
            elif t == "NarrationEvent":
                messages.append(
                    ConversationMessage(
                        seq=env.seq, sim_ts=env.sim_ts, participant="Autopilot", kind="message",
                        text=str(p.get("text", "")), model_id=pending_model,
                    )
                )
            elif t == "ControlEvent":
                messages.append(_control_message(env))

        if records and pending_trials:
            flush_trials(records[-1])

        return ConversationPayload(at_seq=effective, max_seq=max_seq, messages=messages)

    # -- 3D neural-web graph ----------------------------------------------

    def graph(self, *, at_seq: int | None = None) -> GraphPayload:
        """The neural-web graph (docs/11 §11.9), rebuilt from the audit up to
        `at_seq` (inclusive) — passing an earlier seq replays the graph at
        that point in the session, deterministically. Only edges that are
        *honestly derivable* from the audit are emitted: `dataflow`
        (feed→models), `attention` (meta→models it explored), and
        `promotion` (meta→a model that crossed the gate). Live inter-model
        `corr±` edges need per-model concurrent return series (M11) and are
        deliberately omitted rather than faked."""
        max_seq = self._records[-1].seq if self._records else 0
        effective = max_seq if at_seq is None else at_seq
        if at_seq is None:
            # the full-log view -- reuse the shared reconstruction; only the
            # scrubber path (an explicit earlier at_seq) rebuilds a filtered one
            records = self._records
            recon = self._reconstruction()
        else:
            records = [r for r in self._records if r.seq <= effective]
            recon = _Reconstruction(records, self._catalog)
        cells = {c.model_id: c for c in recon.model_cells()}

        promoted: set[str] = set()
        de_risked: set[str] = set()
        explored: set[str] = set()
        attention: dict[str, int] = defaultdict(int)
        meta_present = False
        for env in records:
            t = env.type
            if t == "PromotionEvent":
                model = _model_from_candidate(str(env.payload.get("candidate_id", "")))
                if model:
                    promoted.add(model)
            elif t == "HypothesisEvent":
                meta_present = True
                for m in env.payload.get("target_models") or []:
                    attention[str(m)] += 1
                    explored.add(str(m))
            elif t == "DeRiskEvent":
                for m in env.payload.get("models") or []:
                    de_risked.add(str(m))
            elif t == "LlmCallEvent":
                meta_present = True

        # Model identity comes from both surfaces: trading audits give live
        # cells (state/return/trades); an autopilot audit only names models
        # in its autonomy events. Union them so the graph works for either.
        all_ids = sorted(set(cells) | explored | promoted | de_risked)

        nodes: list[GraphNode] = []
        links: list[GraphLink] = []
        tracked_ids: list[str] = []
        sandbox_ids: list[str] = []

        for model_id in all_ids:
            is_tracked = model_id in promoted
            (tracked_ids if is_tracked else sandbox_ids).append(model_id)
            cell = cells.get(model_id)
            if cell is not None:
                state = cell.state
                sim_return = cell.sim_return_pct if cell.sim_return_pct is not None else 0.0
                n_trades = cell.n_trades
                family = cell.family
                status: ModelStatus = "validated" if is_tracked else cell.status
            else:
                state = "HALTED" if model_id in de_risked else ("FIRED" if is_tracked else "ARMED")
                sim_return, n_trades, family = 0.0, 0, "—"
                status = "validated" if is_tracked else "unproven"
            activity = n_trades or (1 if model_id in explored else 0)
            nodes.append(
                GraphNode(
                    id=model_id, label=model_id, family=family,
                    kind="tracked" if is_tracked else "sandbox", state=state,
                    conviction=_conviction(is_tracked, activity),
                    sim_return=sim_return, n_trades=n_trades, status=status,
                )
            )

        node_ids = {n.id for n in nodes}
        if nodes:
            nodes.append(_structural_node("feed", "Market feed", "regime"))
            for model_id in all_ids:
                links.append(
                    GraphLink(source="feed", target=model_id, kind="dataflow", weight=0.4)
                )

        if meta_present:
            nodes.append(_structural_node("meta", "Meta-layer", "meta"))
            max_att = max(attention.values(), default=1)
            for model_id, count in attention.items():
                if model_id in node_ids:
                    links.append(
                        GraphLink(
                            source="meta", target=model_id, kind="attention",
                            weight=round(count / max_att, 3),
                        )
                    )
            for model_id in sorted(promoted):
                if model_id in node_ids:
                    links.append(
                        GraphLink(source="meta", target=model_id, kind="promotion", weight=1.0)
                    )

        return GraphPayload(
            run_id=self._run_id,
            at_seq=effective,
            max_seq=max_seq,
            nodes=nodes,
            links=links,
            regions={"tracked": tracked_ids, "sandbox": sandbox_ids},
        )


# --- chart/graph helpers ----------------------------------------------------


def _price_bar(env: EventEnvelope) -> PriceBar:
    return PriceBar(
        ts=env.sim_ts,
        o=Decimal(str(env.payload["o"])),
        h=Decimal(str(env.payload["h"])),
        l=Decimal(str(env.payload["l"])),
        c=Decimal(str(env.payload["c"])),
        v=float(env.payload["v"]),
    )


def _equity_point(env: EventEnvelope) -> EquityPoint:
    return EquityPoint(ts=env.sim_ts, equity=Decimal(str(env.payload["equity"])))


def _downsample[T](rows: list[T], max_points: int) -> list[T]:
    """Evenly-strided downsample preserving the first and last point —
    good enough for a chart (the shape survives), not a statistical
    resample. A no-op when already within budget."""
    n = len(rows)
    if n <= max_points or max_points <= 1:
        return rows
    step = (n - 1) / (max_points - 1)
    indices = {round(i * step) for i in range(max_points)}
    return [row for i, row in enumerate(rows) if i in indices]


def blotter_empty_state_reason(snapshot: UIState, rows: list[BlotterRow]) -> str | None:
    """Docs/13 M20 "honest empty state" -- if the blotter has nothing to
    show, say *why*, deterministically from the same snapshot the rest of
    the desk already reads. `None` means non-empty; render the rows
    instead."""
    if rows:
        return None
    if sum(h.bars_seen for h in snapshot.data_health) == 0:
        return "Warming up -- waiting for the first bars to arrive."
    if not any(m.status == "validated" for m in snapshot.models):
        return "Tracked book has 0 promoted models -- exploring in the sandbox."
    return "No signals in the last bars (models are watching)."


def _conviction(is_tracked: bool, n_trades: int) -> float:
    """A display heuristic for node prominence (docs/05 §5.5) — attention/
    evidence, explicitly NOT P&L. Validated (tracked) models read strongest;
    an idle model reads faint."""
    if is_tracked:
        return 0.9
    if n_trades > 0:
        return 0.5
    return 0.2


def _structural_node(node_id: str, label: str, kind: NodeKind) -> GraphNode:
    return GraphNode(
        id=node_id, label=label, family="—", kind=kind, state="ARMED",
        conviction=0.5, sim_return=0.0, n_trades=0, status="unproven",
    )


def _model_from_candidate(candidate_id: str) -> str:
    """`candidate_id` is `cand:<model_id>:<step>` (orchestrator convention)."""
    parts = candidate_id.split(":")
    return parts[1] if len(parts) >= 2 else ""


def _validation_message(env: EventEnvelope, pending_model: str) -> ConversationMessage:
    """docs/13 M21: the Judge's turn -- the only participant whose message
    carries a `verdict`, so the UI can color it long/short by outcome, not
    a fixed hue (the spec's "Judge = long/short by verdict" requirement)."""
    p = env.payload
    result = str(p.get("result", "FAIL"))
    verdict: Literal["PASS", "FAIL"] = "PASS" if result == "PASS" else "FAIL"
    glyph = "✓" if verdict == "PASS" else "✗"
    dsr = float(str(p.get("dsr", "nan")))
    pbo = float(str(p.get("pbo", "nan")))
    reasons = []
    if not p.get("cost_survived", True):
        reasons.append("doesn't survive costs")
    if not p.get("beats_equal_weight", True):
        reasons.append("doesn't beat equal-weight")
    if verdict == "PASS" and not reasons:
        reasons.append("beats equal-weight after costs")
    text = f"{glyph} {verdict} — DSR {dsr:.2f}, PBO {pbo:.2f}"
    if reasons:
        text += ", " + "; ".join(reasons)
    model_id = _model_from_candidate(str(p.get("candidate_id", ""))) or pending_model
    evidence = p.get("evidence") or {}
    detail = ", ".join(f"{k}: {v}" for k, v in evidence.items())
    return ConversationMessage(
        seq=env.seq, sim_ts=env.sim_ts, participant="Judge", kind="card",
        text=text, detail=detail, model_id=model_id, verdict=verdict,
    )


def _control_message(env: EventEnvelope) -> ConversationMessage:
    """docs/13 M21: "kill and de-risk events appear as messages too" --
    the human's own interventions are part of the conversation, not a
    separate silent channel."""
    p = env.payload
    command = str(p.get("command", ""))
    operator = str(p.get("operator", ""))
    note = str(p.get("note", ""))
    is_autopilot_toggle = command in ("AUTOPILOT_ON", "AUTOPILOT_OFF")
    participant: Participant = "Autopilot" if is_autopilot_toggle else "Risk"
    text = command.replace("_", " ").title()
    if operator:
        text += f" — {operator}"
    if note:
        text += f": {note}"
    return ConversationMessage(
        seq=env.seq, sim_ts=env.sim_ts, participant=participant, kind="message", text=text,
    )


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
        self.last_fill_seq = -1  # "FIRED" == filled on the newest record; computed at output time
        self.last_fill_px = Decimal("0")  # V5 M26: stance_pct's notional reference
        self.return_history: list[float] = []  # V5 M26: bounded sparkline, see _SPARKLINE_CAP
        self._lots: list[tuple[Decimal, Decimal]] = []  # (qty, px) FIFO, long-only round trips

    def clone(self) -> _StrategyAgg:
        c = _StrategyAgg()
        c.net_qty = self.net_qty
        c.n_trades = self.n_trades
        c.realized = self.realized
        c.last_reason = self.last_reason
        c.last_direction = self.last_direction
        c.last_fill_seq = self.last_fill_seq
        c.last_fill_px = self.last_fill_px
        c.return_history = list(self.return_history)
        c._lots = list(self._lots)
        return c

    def record_sample(self, sample: float) -> None:
        self.return_history.append(sample)
        if len(self.return_history) > _SPARKLINE_CAP:
            del self.return_history[: len(self.return_history) - _SPARKLINE_CAP]

    def on_buy(self, qty: Decimal, px: Decimal, fee: Decimal) -> None:
        self._lots.append((qty, px))
        self.net_qty += qty
        self.realized -= fee
        self.n_trades += 1
        self.last_fill_px = px

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
        self.last_fill_px = px


class _Reconstruction:
    def __init__(self, records: list[EventEnvelope], catalog: dict[str, CatalogModelInfo]) -> None:
        self._records = records
        self._catalog = catalog
        self._max_seq = records[-1].seq if records else 0

        self._order_to_strategy: dict[str, str] = {}
        self._order_to_side: dict[str, str] = {}
        self._order_to_intent: dict[str, str] = {}
        self._intent_to_strategy: dict[str, str] = {}
        self._intent_meta: dict[str, dict[str, Any]] = {}
        self._decision_meta: dict[str, dict[str, Any]] = {}
        self._decision_seq: dict[str, int] = {}
        self._decision_ts: dict[str, datetime] = {}
        self._fill_pnl: dict[int, Decimal] = {}
        self._fill_envs: list[EventEnvelope] = []
        self._strategies: dict[str, _StrategyAgg] = defaultdict(_StrategyAgg)
        self._last_risk_state: dict[str, object] | None = None
        self._starting_equity: Decimal | None = None
        self._symbols: dict[Symbol, tuple[datetime | None, int]] = {}
        self.kill_active = False
        self.breaches: list[str] = []

        self._walk(self._records)

    def _walk(self, records: list[EventEnvelope]) -> None:
        for env in records:
            handler = getattr(self, f"_on_{env.type}", None)
            if handler is not None:
                handler(env)

    def extended(
        self, new_records: list[EventEnvelope], all_records: list[EventEnvelope]
    ) -> _Reconstruction:
        """A NEW reconstruction covering `all_records` (= this one's records
        + `new_records`), built by copying this one's aggregation state and
        walking only the tail -- O(new + trades) instead of O(total
        records) per poll (perf phase 2b). This instance is never mutated,
        so in-flight readers on other threads stay consistent."""
        clone = object.__new__(_Reconstruction)
        clone._records = all_records
        clone._catalog = self._catalog  # read-only mapping, safe to share
        clone._max_seq = self._max_seq
        clone._order_to_strategy = dict(self._order_to_strategy)
        clone._order_to_side = dict(self._order_to_side)
        clone._order_to_intent = dict(self._order_to_intent)
        clone._intent_to_strategy = dict(self._intent_to_strategy)
        clone._intent_meta = dict(self._intent_meta)
        clone._decision_meta = dict(self._decision_meta)
        clone._decision_seq = dict(self._decision_seq)
        clone._decision_ts = dict(self._decision_ts)
        clone._fill_pnl = dict(self._fill_pnl)
        clone._fill_envs = list(self._fill_envs)
        clone._strategies = defaultdict(
            _StrategyAgg, {k: v.clone() for k, v in self._strategies.items()}
        )
        clone._last_risk_state = (
            dict(self._last_risk_state) if self._last_risk_state is not None else None
        )
        clone._starting_equity = self._starting_equity
        clone._symbols = dict(self._symbols)
        clone.kill_active = self.kill_active
        clone.breaches = list(self.breaches)

        if new_records:
            clone._max_seq = new_records[-1].seq
        clone._walk(new_records)
        return clone

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
        self._intent_meta[str(p["intent_id"])] = dict(p)

    def _on_RiskDecision(self, env: EventEnvelope) -> None:
        p = env.payload
        intent_ref = str(p["intent_ref"])
        self._decision_meta[intent_ref] = dict(p)
        self._decision_seq[intent_ref] = env.seq
        self._decision_ts[intent_ref] = env.sim_ts

    def _on_Order(self, env: EventEnvelope) -> None:
        p = env.payload
        order_id = str(p["order_id"])
        intent_ref = str(p["intent_ref"])
        strategy = self._intent_to_strategy.get(intent_ref)
        if strategy is not None:
            self._order_to_strategy[order_id] = strategy
        self._order_to_side[order_id] = str(p["side"])
        self._order_to_intent[order_id] = intent_ref

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
        realized_before = agg.realized
        if side == "BUY":
            agg.on_buy(qty, px, fee)
        else:
            agg.on_sell(qty, px, fee)
        agg.last_fill_seq = env.seq
        self._fill_pnl[env.seq] = agg.realized - realized_before
        self._fill_envs.append(env)
        sample = _sim_return_pct(agg, self._starting_equity)
        if sample is not None:
            agg.record_sample(sample)

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
        current_equity = (
            Decimal(str(self._last_risk_state["equity"])) if self._last_risk_state else None
        )
        cells = []
        for model_id in ids:
            info = self._catalog.get(model_id)
            agg = self._strategies.get(model_id)
            family = info.family if info else "unknown"
            sleeve = info.sleeve if info else "unknown"
            status: ModelStatus = info.status if info else "unproven"
            state = _model_state(agg, kill_active=self.kill_active, max_seq=self._max_seq)
            sim_return = _sim_return_pct(agg, self._starting_equity)
            cells.append(
                ModelCell(
                    model_id=model_id,
                    family=family,
                    sleeve=sleeve,
                    state=state,
                    status=status,
                    sim_return_pct=sim_return,
                    n_trades=agg.n_trades if agg else 0,
                    last_reason=agg.last_reason if agg else "",
                    sparkline_pct=list(agg.return_history) if agg else [],
                    stance_pct=_stance_pct(agg, current_equity),
                )
            )
        return cells

    def data_health(self) -> list[DataHealth]:
        return [
            DataHealth(symbol=sym, last_bar=last, bars_seen=seen)
            for sym, (last, seen) in sorted(self._symbols.items())
        ]

    def blotter(self) -> list[BlotterRow]:
        """The full order lifecycle, one row per fill; a `REJECT`ed (or
        approved-but-not-yet-filled) intent gets exactly one no-fill row.
        Oldest first (same convention as `tape()`); the UI reverses for
        display."""
        rows: list[BlotterRow] = []
        filled_intents: set[str] = set()

        for env in self._fill_envs:
            p = env.payload
            order_id = str(p["order_id"])
            intent_ref = self._order_to_intent.get(order_id)
            intent = self._intent_meta.get(intent_ref) if intent_ref else None
            decision = self._decision_meta.get(intent_ref) if intent_ref else None
            if intent is None or decision is None or intent_ref is None:
                continue  # not honestly reconstructable from this audit log
            filled_intents.add(intent_ref)
            rows.append(
                BlotterRow(
                    seq=env.seq, sim_ts=env.sim_ts,
                    model=str(intent["strategy"]), symbol=str(intent["symbol"]),
                    side=intent["side"], intent_qty=Decimal(str(intent["qty"])),
                    reason=str(intent.get("reason", "")),
                    verdict=decision["verdict"], rule_hits=list(decision.get("rule_hits", [])),
                    fill_qty=Decimal(str(p["fill_qty"])), fill_px=Decimal(str(p["fill_px"])),
                    fee=Decimal(str(p["fee"])), slippage_bps=float(p["slippage_bps"]),
                    partial=bool(p["partial"]), sim_pnl=self._fill_pnl.get(env.seq),
                )
            )

        for intent_ref, decision in self._decision_meta.items():
            if intent_ref in filled_intents:
                continue
            intent = self._intent_meta.get(intent_ref)
            if intent is None:
                continue
            rows.append(
                BlotterRow(
                    seq=self._decision_seq[intent_ref], sim_ts=self._decision_ts[intent_ref],
                    model=str(intent["strategy"]), symbol=str(intent["symbol"]),
                    side=intent["side"], intent_qty=Decimal(str(intent["qty"])),
                    reason=str(intent.get("reason", "")),
                    verdict=decision["verdict"], rule_hits=list(decision.get("rule_hits", [])),
                    fill_qty=None, fill_px=None, fee=None, slippage_bps=None,
                    partial=False, sim_pnl=None,
                )
            )

        rows.sort(key=lambda r: r.seq)
        return rows

    def reconciliation(self) -> list[ReconciliationRow]:
        """Per-model position + realized P&L, tied out to the same FIFO
        lot accounting `model_cells()` reads from -- one source of truth,
        not a second computation that could silently diverge."""
        return [
            ReconciliationRow(
                model_id=model_id, net_qty=agg.net_qty, realized_pnl=agg.realized,
                n_trades=agg.n_trades,
            )
            for model_id, agg in sorted(self._strategies.items())
        ]


def _model_state(agg: _StrategyAgg | None, *, kill_active: bool, max_seq: int) -> ModelState:
    if kill_active:
        return "HALTED"
    if agg is None or agg.net_qty == 0:
        return "ARMED"
    if agg.last_fill_seq == max_seq:
        return "FIRED"
    return "LONG" if agg.net_qty > 0 else "SHORT"


def _sim_return_pct(agg: _StrategyAgg | None, starting_equity: Decimal | None) -> float | None:
    if agg is None or agg.n_trades == 0 or starting_equity is None or starting_equity <= 0:
        return None
    return float(agg.realized / starting_equity * 100)


def _stance_pct(agg: _StrategyAgg | None, equity: Decimal | None) -> float:
    """V5 M26 living cells: how much of *current* equity this model's open
    position represents, in [0, 1]. Deliberately not "% of a per-strategy
    risk budget" -- that config value lives in `risk/rules.py`, outside
    what `StateReader` can see (it only ever replays the audit log), so
    this uses only data the log itself carries: the position's own last
    fill price times its net qty, against equity from the latest
    `RiskStateEvent`. Long-only engine (GUARDRAILS: no SHORT) -- a plain
    0-100% fill, never a bidirectional long/short bar."""
    if agg is None or equity is None or equity <= 0 or agg.net_qty <= 0:
        return 0.0
    notional = agg.net_qty * agg.last_fill_px
    return max(0.0, min(1.0, float(notional / equity)))


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
