"""The 12 MVP risk rules (docs/archive/11 §11.3). Each rule is a small,
pure function of `(intent, state, config)` returning a `RuleHit` (or
`None` if it doesn't fire). `RiskModel.check` composes them: a hard
`REJECT` short-circuits the whole check; `CLAMP` hits accumulate and the
tightest one wins. Unknown/misconfigured inputs fail closed — a rule that
can't determine safety returns `REJECT`, never `APPROVE` by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from lqe.core.events import OrderIntent
from lqe.core.types import Symbol


@dataclass(frozen=True)
class RiskConfig:
    max_daily_loss: Decimal = Decimal("1000000")
    max_pos_symbol: Decimal = Decimal("1000000")
    max_gross_exposure: Decimal = Decimal("1.0")
    max_orders_per_day: int = 1000
    max_orders_per_min: int = 60
    symbol_whitelist: frozenset[Symbol] = field(default_factory=frozenset)  # empty = allow all
    max_staleness: timedelta = timedelta(minutes=5)
    max_price_deviation: Decimal = Decimal("0.2")
    per_strategy_budget: Decimal = Decimal("1.0")
    max_dd: Decimal = Decimal("1.0")
    # V5 M27 (Universe Core): fraction of *portfolio-wide* equity a single
    # sleeve may have deployed across every instrument's book at once.
    # Permissive default (100%) so a single-sleeve/single-symbol book's
    # behavior is unchanged unless a caller deliberately tightens it.
    max_sleeve_gross: Decimal = Decimal("1.0")


@dataclass(frozen=True)
class PortfolioState:
    symbol: Symbol
    equity: Decimal
    cash: Decimal
    peak_equity: Decimal
    daily_pnl: Decimal
    position_qty: Decimal
    reference_price: Decimal
    last_data_ts: datetime
    now_ts: datetime
    recent_order_ts: tuple[datetime, ...] = ()
    recent_intent_keys: frozenset[str] = frozenset()
    strategy_notional_used: Decimal = Decimal("0")
    open_orders: int = 0
    kill_active: bool = False
    # V5 M27: cross-instrument aggregate figures, populated only when a
    # multi-instrument orchestrator shares a `risk.portfolio_context.
    # PortfolioContext` across several single-symbol `Session`s (see
    # `backtest/universe_runner.py`). `None` in the ordinary single-book
    # case -- `check_portfolio_gross_exposure`/`check_sleeve_concentration`
    # are then no-ops, so nothing about the existing single-symbol/single-
    # book risk behavior changes.
    portfolio_equity: Decimal | None = None
    portfolio_gross_notional: Decimal | None = None
    sleeve_notional_used: Decimal | None = None

    @property
    def gross_exposure(self) -> Decimal:
        if self.equity <= 0:
            return Decimal("0")
        return abs(self.position_qty) * self.reference_price / self.equity


@dataclass(frozen=True)
class RuleHit:
    rule: str
    verdict: Literal["REJECT", "CLAMP"]
    clamp_qty: Decimal | None = None
    detail: str = ""


_State = PortfolioState
_Config = RiskConfig


def check_kill_switch(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    """Once killed, no *risk-increasing* order may be emitted (docs/archive/
    14 §14.5) — a SELL that reduces or flattens an existing long is still
    allowed (even the point of a FLATTEN), only a BUY (or a SELL that would
    exceed the held qty, i.e. attempt to go net-short) is blocked."""
    if not state.kill_active:
        return None
    if intent.side == "SELL" and intent.qty <= state.position_qty:
        return None
    return RuleHit(
        rule="kill_switch_active", verdict="REJECT",
        detail="kill switch is active — risk-increasing order blocked",
    )


def check_max_drawdown(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if state.peak_equity <= 0:
        return None
    drawdown = (state.peak_equity - state.equity) / state.peak_equity
    if drawdown >= config.max_dd:
        detail = f"drawdown {drawdown:.4f} >= max_dd {config.max_dd}"
        return RuleHit(rule="max_drawdown", verdict="REJECT", detail=detail)
    return None


def check_daily_loss(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if state.daily_pnl <= -config.max_daily_loss:
        detail = f"daily_pnl {state.daily_pnl} <= -{config.max_daily_loss}"
        return RuleHit(rule="max_daily_loss", verdict="REJECT", detail=detail)
    return None


def check_symbol_whitelist(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if config.symbol_whitelist and intent.symbol not in config.symbol_whitelist:
        detail = f"{intent.symbol} not whitelisted"
        return RuleHit(rule="symbol_whitelist", verdict="REJECT", detail=detail)
    return None


def check_stale_data(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if state.now_ts - state.last_data_ts > config.max_staleness:
        return RuleHit(rule="stale_data", verdict="REJECT", detail="data older than max_staleness")
    return None


def check_duplicate_signal(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if intent.idempotency_key in state.recent_intent_keys:
        detail = f"duplicate idempotency_key {intent.idempotency_key}"
        return RuleHit(rule="duplicate_signal", verdict="REJECT", detail=detail)
    return None


def check_sane_price_qty(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if intent.qty <= 0 or not intent.qty.is_finite():
        detail = f"non-finite/non-positive qty {intent.qty}"
        return RuleHit(rule="sane_qty", verdict="REJECT", detail=detail)
    if intent.limit_px is not None and (intent.limit_px <= 0 or not intent.limit_px.is_finite()):
        detail = f"non-finite/non-positive limit_px {intent.limit_px}"
        return RuleHit(rule="sane_price", verdict="REJECT", detail=detail)
    if state.reference_price > 0:
        check_px = intent.limit_px if intent.limit_px is not None else state.reference_price
        deviation = abs(check_px - state.reference_price) / state.reference_price
        if deviation > config.max_price_deviation:
            detail = (
                f"price {check_px} deviates {deviation:.4f} "
                f"from reference {state.reference_price}"
            )
            return RuleHit(rule="sane_price", verdict="REJECT", detail=detail)
    return None


def check_order_rate(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    one_day_ago = state.now_ts - timedelta(days=1)
    day_count = sum(1 for ts in state.recent_order_ts if ts >= one_day_ago)
    if day_count >= config.max_orders_per_day:
        detail = f"{day_count} orders in the last day"
        return RuleHit(rule="max_orders_per_day", verdict="REJECT", detail=detail)
    one_min_ago = state.now_ts - timedelta(minutes=1)
    min_count = sum(1 for ts in state.recent_order_ts if ts >= one_min_ago)
    if min_count >= config.max_orders_per_min:
        detail = f"{min_count} orders in the last minute"
        return RuleHit(rule="max_orders_per_min", verdict="REJECT", detail=detail)
    return None


def check_max_position(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if intent.side != "BUY":
        return None
    projected = state.position_qty + intent.qty
    if projected <= config.max_pos_symbol:
        return None
    allowed = config.max_pos_symbol - state.position_qty
    if allowed <= 0:
        return RuleHit(rule="max_pos_symbol", verdict="REJECT", detail="at/over max_pos_symbol")
    return RuleHit(rule="max_pos_symbol", verdict="CLAMP", clamp_qty=allowed, detail="clamped")


def check_max_gross_exposure(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if intent.side != "BUY" or state.equity <= 0 or state.reference_price <= 0:
        return None
    projected_notional = (state.position_qty + intent.qty) * state.reference_price
    max_notional = config.max_gross_exposure * state.equity
    if projected_notional <= max_notional:
        return None
    allowed_notional = max_notional - state.position_qty * state.reference_price
    if allowed_notional <= 0:
        return RuleHit(rule="max_gross_exposure", verdict="REJECT", detail="at/over max exposure")
    return RuleHit(
        rule="max_gross_exposure", verdict="CLAMP",
        clamp_qty=allowed_notional / state.reference_price, detail="clamped",
    )


def check_cash_sufficiency(intent: OrderIntent, state: _State, config: _Config) -> RuleHit | None:
    if intent.side != "BUY":
        return None
    price = intent.limit_px if intent.limit_px is not None else state.reference_price
    if price <= 0:
        return RuleHit(rule="cash_sufficiency", verdict="REJECT", detail="no reference price")
    required = intent.qty * price
    if required <= state.cash:
        return None
    allowed_qty = state.cash / price
    if allowed_qty <= 0:
        return RuleHit(rule="cash_sufficiency", verdict="REJECT", detail="insufficient cash")
    return RuleHit(
        rule="cash_sufficiency", verdict="CLAMP", clamp_qty=allowed_qty, detail="clamped"
    )


def check_per_strategy_budget(
    intent: OrderIntent, state: _State, config: _Config
) -> RuleHit | None:
    if intent.side != "BUY" or state.equity <= 0 or state.reference_price <= 0:
        return None
    projected = state.strategy_notional_used + intent.qty * state.reference_price
    max_notional = config.per_strategy_budget * state.equity
    if projected <= max_notional:
        return None
    allowed_notional = max_notional - state.strategy_notional_used
    if allowed_notional <= 0:
        return RuleHit(rule="per_strategy_budget", verdict="REJECT", detail="budget exhausted")
    return RuleHit(
        rule="per_strategy_budget", verdict="CLAMP",
        clamp_qty=allowed_notional / state.reference_price, detail="clamped",
    )


def check_portfolio_gross_exposure(
    intent: OrderIntent, state: _State, config: _Config
) -> RuleHit | None:
    """V5 M27: the cross-instrument counterpart to `check_max_gross_exposure`
    -- caps total notional across every book in the universe against total
    portfolio equity, not just this one book's own position/equity. A
    no-op (returns `None`) unless a multi-instrument orchestrator has
    populated `state.portfolio_equity`/`state.portfolio_gross_notional`
    (both `None` in the single-book case)."""
    if (
        intent.side != "BUY"
        or state.portfolio_equity is None
        or state.portfolio_gross_notional is None
        or state.portfolio_equity <= 0
        or state.reference_price <= 0
    ):
        return None
    projected_notional = state.portfolio_gross_notional + intent.qty * state.reference_price
    max_notional = config.max_gross_exposure * state.portfolio_equity
    if projected_notional <= max_notional:
        return None
    allowed_notional = max_notional - state.portfolio_gross_notional
    if allowed_notional <= 0:
        return RuleHit(
            rule="portfolio_gross_exposure", verdict="REJECT",
            detail="at/over portfolio-wide max exposure",
        )
    return RuleHit(
        rule="portfolio_gross_exposure", verdict="CLAMP",
        clamp_qty=allowed_notional / state.reference_price, detail="clamped",
    )


def check_sleeve_concentration(
    intent: OrderIntent, state: _State, config: _Config
) -> RuleHit | None:
    """V5 M27: caps how much of total portfolio equity a single return-
    driver sleeve (e.g. `trend_momentum`) may have deployed across every
    instrument's book at once -- a no-op unless a multi-instrument
    orchestrator has populated `state.sleeve_notional_used`/
    `state.portfolio_equity` (both `None` in the single-book case, same
    backward-compat pattern as `check_portfolio_gross_exposure`)."""
    if (
        intent.side != "BUY"
        or state.sleeve_notional_used is None
        or state.portfolio_equity is None
        or state.portfolio_equity <= 0
        or state.reference_price <= 0
    ):
        return None
    projected = state.sleeve_notional_used + intent.qty * state.reference_price
    max_notional = config.max_sleeve_gross * state.portfolio_equity
    if projected <= max_notional:
        return None
    allowed_notional = max_notional - state.sleeve_notional_used
    if allowed_notional <= 0:
        return RuleHit(rule="sleeve_concentration", verdict="REJECT", detail="sleeve cap exhausted")
    return RuleHit(
        rule="sleeve_concentration", verdict="CLAMP",
        clamp_qty=allowed_notional / state.reference_price, detail="clamped",
    )


# Order matters only for which REJECT reason is reported first on a hard
# breach; every rule still runs against APPROVE/CLAMP accumulation.
ALL_RULES = (
    check_kill_switch,
    check_max_drawdown,
    check_daily_loss,
    check_symbol_whitelist,
    check_stale_data,
    check_duplicate_signal,
    check_sane_price_qty,
    check_order_rate,
    check_max_position,
    check_max_gross_exposure,
    check_cash_sufficiency,
    check_per_strategy_budget,
    check_portfolio_gross_exposure,
    check_sleeve_concentration,
)
