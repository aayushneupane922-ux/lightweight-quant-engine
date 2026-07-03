"""Immutable event payloads + the hash-chained envelope (docs/11 §11.3).

Every payload model is frozen (construct-once, never mutated). The
`EventEnvelope` is what actually gets hash-chained and audited; a payload
by itself is just data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lqe.core.types import Book, Bps, Price, Qty, Symbol, Timeframe

_FROZEN = ConfigDict(frozen=True)


class EventPayload(BaseModel):
    model_config = _FROZEN


# --- trading events -----------------------------------------------------


class MarketEvent(EventPayload):
    exchange: str
    symbol: Symbol
    timeframe: Timeframe
    ts_open: datetime
    o: Price
    h: Price
    l: Price  # noqa: E741 — matches the docs/11 §11.3 wire field name for "low"
    c: Price
    v: float
    bid: Price | None = None
    ask: Price | None = None
    source_version: str


class SignalEvent(EventPayload):
    strategy: str
    symbol: Symbol
    direction: Literal["LONG", "SHORT", "FLAT"]
    strength: float
    intent_kind: Literal["ENTER", "EXIT", "REBALANCE"]
    bar_ts: datetime
    reason: str


class OrderIntent(EventPayload):
    intent_id: str
    signal_ref: str
    strategy: str
    symbol: Symbol
    side: Literal["BUY", "SELL"]
    qty: Qty
    order_type: Literal["MARKET", "LIMIT"]
    limit_px: Price | None = None
    idempotency_key: str
    reason: str


class RiskDecision(EventPayload):
    intent_ref: str
    verdict: Literal["APPROVE", "CLAMP", "REJECT"]
    approved_qty: Qty
    rule_hits: list[str] = []
    detail: str = ""


class Order(EventPayload):
    order_id: str
    intent_ref: str
    side: Literal["BUY", "SELL"]
    qty: Qty
    order_type: Literal["MARKET", "LIMIT"]
    limit_px: Price | None = None
    status: Literal[
        "PENDING", "ACCEPTED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"
    ]


class FillEvent(EventPayload):
    order_id: str
    fill_ts: datetime
    fill_px: Price
    fill_qty: Qty
    fee: Price
    slippage_bps: Bps
    partial: bool


class PositionEvent(EventPayload):
    symbol: Symbol
    qty: Qty
    avg_px: Price
    realized_pnl: Price
    unrealized_pnl: Price
    fees_paid: Price


class RiskStateEvent(EventPayload):
    equity: Price
    cash: Price
    daily_pnl: Price
    gross_exposure: Price
    peak_equity: Price
    drawdown: float
    open_orders: int
    breaches: list[str] = []
    kill_active: bool


class ControlEvent(EventPayload):
    command: Literal[
        "START", "STOP", "KILL", "FREEZE", "FLATTEN", "AUTOPILOT_ON", "AUTOPILOT_OFF"
    ]
    source: str
    operator: str
    note: str = ""


# --- autonomy events ------------------------------------------------------


class HypothesisEvent(EventPayload):
    hypo_id: str
    rationale: str
    target_models: list[str]
    proposed_space: dict[str, Any]
    regime: str


class TrialEvent(EventPayload):
    trial_id: str
    hypo_id: str
    study_id: str
    params: dict[str, Any]
    oos_metric: float
    seed: int
    index: int


class ValidationEvent(EventPayload):
    candidate_id: str
    result: Literal["PASS", "FAIL"]
    dsr: float
    pbo: float
    cost_survived: bool
    beats_equal_weight: bool
    evidence: dict[str, Any]


class PromotionEvent(EventPayload):
    candidate_id: str
    from_book: Literal["sandbox"]
    to_book: Literal["tracked"]
    config_version: str


class DeRiskEvent(EventPayload):
    reason: str
    models: list[str]
    action: Literal["REDUCE", "PAUSE", "RETIRE"]


class NarrationEvent(EventPayload):
    text: str
    refs: list[str] = []


# --- envelope --------------------------------------------------------------


class EventEnvelope(BaseModel):
    """The hash-chained wrapper every event is audited as (docs/11 §11.3)."""

    model_config = _FROZEN

    event_id: str
    run_id: str
    seq: int
    book: Book
    sim_ts: datetime
    wall_ts: datetime
    type: str
    prev_hash: str
    hash: str
    payload: dict[str, Any]
