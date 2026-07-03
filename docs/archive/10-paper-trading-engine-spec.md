# 10 — Paper-Trading Engine Spec

**Mandate:** a deterministic, event-driven, fully-simulated trading subsystem. **It is structurally impossible for this system to place a real order in the MVP.** The paper broker is the *only* `ExecutionAdapter` that exists; real adapters are absent from the codebase and guarded (see §10.12, [`14`](14-safety-risk-and-compliance-review.md)).

## 10.1 Event-driven architecture

Single-threaded loop draining a time-ordered queue. Events are immutable, timestamped, and appended to the audit log as they flow. Same loop for backtest (`ReplayClock`) and paper (`WallclockClock`) — see [`05`](05-recommended-architecture.md) §5.4.

```
Clock → MarketEvent → Strategy.on_market → [SignalEvent] → Portfolio/Sizing
   → OrderIntent → RiskEngine.check → (APPROVE) → Order → PaperBroker
   → FillSimulator → FillEvent → Portfolio update → Strategy.on_fill → audit
                                   (REJECT/CLAMP) → audit, no order
```

## 10.2 Event types

| Event | Fields (core) | Emitted by |
|---|---|---|
| `MarketEvent` | ts, exchange, symbol, timeframe, OHLCV, (opt) bid/ask | MarketDataAdapter |
| `SignalEvent` | ts, strategy, symbol, direction, strength, intent_kind | Strategy |
| `OrderIntent` | ts, strategy, symbol, side, qty, type(mkt/limit), limit_px, reason | Portfolio/Sizing |
| `RiskDecision` | intent_ref, verdict(APPROVE/REJECT/CLAMP), clamped_qty, rule_hits[] | RiskEngine |
| `Order` | order_id, intent_ref, side, qty, type, limit_px, status | Engine (post-risk) |
| `FillEvent` | order_id, ts, fill_px, fill_qty, fee, slippage, partial? | FillSimulator |
| `RejectEvent` | order_id/intent_ref, reason | Risk or Broker |
| `PositionEvent` | symbol, qty, avg_px, realized_pnl, unrealized_pnl | Portfolio |
| `RiskStateEvent` | daily_pnl, exposure, breaches[], kill_active | RiskEngine |
| `ControlEvent` | START/STOP/**KILL**/FLATTEN, source(ui/daemon) | UI/daemon |

All events carry `run_id`, `seq` (monotonic), and `event_id` for the audit log and replay.

## 10.3 Order intent model

An `OrderIntent` is a *request*, not an order. It must reference the `SignalEvent` and strategy that produced it and a human-readable `reason`. It becomes an `Order` **only** after `RiskEngine.check()` returns APPROVE (or CLAMP with adjusted qty). There is no code path from `SignalEvent` to `Order` that bypasses the risk gate — enforced by a single choke-point function and a test asserting it.

## 10.4 Order state machine

```
            ┌─────────┐  risk REJECT   ┌──────────┐
 intent ──► │ PENDING  │ ─────────────► │ REJECTED │ (terminal)
            └────┬─────┘                └──────────┘
     risk APPROVE│
                 ▼
            ┌─────────┐   cancel        ┌──────────┐
            │ ACCEPTED │ ──────────────►│ CANCELLED │ (terminal)
            └────┬─────┘                └──────────┘
      (sim)      │ partial fill
                 ▼
            ┌───────────────┐  fills complete   ┌────────┐
            │ PARTIALLY_FILLED│ ───────────────►│ FILLED │ (terminal)
            └───────────────┘                   └────────┘
                 │ expire (limit)
                 ▼
            ┌──────────┐
            │ EXPIRED  │ (terminal)
            └──────────┘
```

Illegal transitions raise and are logged. Every transition is an audit record.

## 10.5 Fill simulator

Deterministic, **pessimistic by default**. Configurable model:
- **Market orders:** fill at **next bar open** (default) ± slippage; optionally worst-of next-bar range for conservatism.
- **Limit orders:** fill only if the bar's range trades through the limit; else remain ACCEPTED until expiry.
- **Partial fills:** cap fill qty at a configurable fraction of bar volume (liquidity realism); remainder stays working.
- **Latency:** optional fixed/█random(seeded) delay between order and eligibility.
- **No look-ahead:** the simulator may only use information available at/after the order's eligible time.

Output `FillEvent` includes realized slippage and fee so analytics can attribute cost.

## 10.6 Slippage & commission models (pluggable)

- `SlippageModel`: `fixed_bps`, `spread_based`, `volume_participation`. Default `fixed_bps` (pessimistic) + spread when quotes available.
- `CommissionModel`: per-exchange bps (e.g., crypto taker ~0.1–0.25%); `min_fee`; maker/taker distinction later.
- Both are the **same objects** used in backtests — parity by construction.

## 10.7 Accounting (position, cash, portfolio)

- **Position accounting:** per symbol — qty, avg entry px, realized & unrealized PnL, fees paid. Long/short supported; crypto MVP may restrict to long/flat by config.
- **Cash accounting:** starting cash; debit/credit on fills incl. fees; no negative cash unless margin explicitly enabled (MVP: **cash only, no leverage** by default).
- **Portfolio accounting:** aggregate equity = cash + Σ mark-to-market positions; equity curve sampled per bar; exposure = Σ|position value| / equity.
- **Marking:** mark to last trade/close; stale marks flagged (see §10.9).
- All balances are `Decimal`-based or carefully-rounded floats with documented precision to avoid drift; reconciled each bar (§10.10).

## 10.8 Risk checks (every order — summary; full spec [`11`](11-risk-engine-spec.md))

The risk engine is invoked on **every** `OrderIntent`. MVP checks: kill-switch active, daily-loss limit, max position (per symbol & gross), max order count/rate, symbol whitelist, stale-data guard, duplicate-signal guard, cash sufficiency, sane price/qty. Verdict APPROVE / CLAMP / REJECT, always audited.

## 10.9 Stale-data & duplicate-signal protection

- **Stale-data check:** if the latest market data for a symbol is older than `max_staleness` (e.g., > N× timeframe), **reject new orders** on that symbol and flag `DATA_STALE`. Prevents trading on a frozen/disconnected feed. Bad/late data ⇒ *no trade*, logged.
- **Duplicate-signal prevention:** dedupe identical (strategy, symbol, side, bar) signals within a window; idempotency key on intents prevents double-submission after a retry/restart.

## 10.10 Reconciliation

Each bar (and on shutdown): recompute equity from cash + positions independently and assert it matches the running ledger within tolerance; assert Σ fills == position deltas; assert no orphan orders. Mismatch → halt + loud audit entry. On restart, rebuild state from the audit log and reconcile before accepting new signals.

## 10.11 Audit log

Append-only **JSONL** (one event per line), plus a mirrored table in DuckDB for querying. Every event (§10.2) is recorded with `run_id`, `seq`, `event_id`, wall + sim time, and full payload. The audit log is (a) the source of truth for the daily report, (b) the input to reconciliation/replay, and (c) tamper-evident via per-record hash chaining (each record includes hash of the previous). See [`12`](12-event-and-storage-schema.md).

## 10.12 Kill switch & control

- **Kill switch** (`ControlEvent KILL`): immediately stops new order generation, cancels working orders, optionally **FLATTEN**s positions (paper), and sets `kill_active=true` persisted to disk. Nothing clears it but explicit operator action. Reachable from the UI with one click and from a CLI/file flag.
- **Daily reset** re-arms limits at a configured session boundary; kill state does **not** auto-clear.
- The daemon checks `kill_active` before every order and at every loop tick.

## 10.13 Daily paper-trading report

Generated from the audit log at session end (and on demand): starting/ending equity, PnL, # trades, win/loss, turnover, max intraday DD, fees, risk breaches, rejected orders w/ reasons, data-quality flags (gaps/stale), and reconciliation status. Rendered in the UI ([`13`](13-lightweight-ui-spec.md)) and saved as markdown/HTML.

## 10.14 Deterministic replay

Given a run's recorded market events + config + seed, re-running reproduces identical orders/fills/PnL. Replay is used for: debugging, the backtest↔paper parity test, and audit. Any non-determinism (unseeded RNG, wall-clock reads, dict-ordering reliance, network variability leaking into decisions) is a **bug**, caught by a replay-equality test in CI.

## 10.15 Interfaces (paper broker & execution adapter)

```python
class ExecutionAdapter(Protocol):
    is_paper: bool                 # MVP invariant: MUST be True (asserted at startup)
    def submit(self, order: Order) -> None: ...
    def cancel(self, order_id: str) -> None: ...
    def working_orders(self) -> list[Order]: ...

class PaperBroker(ExecutionAdapter):        # the ONLY implementation in MVP
    is_paper = True
    # owns FillSimulator, SlippageModel, CommissionModel; emits FillEvent/RejectEvent
```

**Live lockout (structural):**
- No `BrokerExecutionAdapter` / real-order code exists in the MVP repo (only a `NotImplementedError` stub behind a disabled feature flag).
- Startup assertion: `assert execution_adapter.is_paper is True` or the engine refuses to run.
- Config schema forbids `mode: live`; a `LIVE_TRADING_ENABLED=false` constant is compiled-in and there is no supported way to flip it in MVP.
- Tests assert: (a) only `PaperBroker` implements `ExecutionAdapter`; (b) no import of any broker SDK; (c) no network call can submit an order. See [`14`](14-safety-risk-and-compliance-review.md) and review prompts [`19`](19-claude-code-review-prompts.md).

> **Design intent restated:** every dangerous capability (real orders, credentials, live mode) is *absent*, not merely *disabled*. You cannot accidentally trade what you did not build.
