# 11 — Risk Engine Spec

**Mandate (constraint #5):** *every* order intent passes through the risk engine. It is a hard, single choke-point gate — not advisory. It returns APPROVE, CLAMP (reduce size to comply), or REJECT, and every decision is audited. In the MVP it protects a paper account; the same gate protects any future real account, so it is built to real standards now.

## 11.1 Position in the flow

```
SignalEvent → Portfolio/Sizing → OrderIntent ──► RiskEngine.check(intent, state) ──►
     APPROVE → Order → PaperBroker
     CLAMP   → Order (reduced qty) → PaperBroker   [+audit rule_hits]
     REJECT  → RejectEvent → audit (no order)
```

There is exactly one function that turns an `OrderIntent` into an `Order`, and it calls `RiskEngine.check()` first. A unit test asserts no other path constructs an `Order`.

## 11.2 Interface

```python
@dataclass(frozen=True)
class RiskDecision:
    verdict: Literal["APPROVE","CLAMP","REJECT"]
    approved_qty: float
    rule_hits: list[str]            # names of rules that fired
    detail: dict                    # numbers behind the decision

class RiskEngine(Protocol):
    def check(self, intent: OrderIntent, state: PortfolioState) -> RiskDecision: ...
    def on_bar(self, state: PortfolioState) -> RiskStateEvent: ...   # recompute limits/breaches
    @property
    def kill_active(self) -> bool: ...
```

Rules are ordered, composable predicates; the engine short-circuits to REJECT on the first hard breach, accumulates soft-clamp adjustments otherwise. Config-driven thresholds (validated by pydantic).

## 11.3 MVP rule set (all enforced on every intent)

| # | Rule | Type | Behavior on breach |
|---|---|---|---|
| 1 | **Kill switch active** | hard | REJECT all new orders; only FLATTEN/cancel allowed |
| 2 | **Daily loss limit** | hard | If realized+unrealized daily PnL ≤ −`max_daily_loss` → REJECT new risk-increasing orders; optionally auto-KILL |
| 3 | **Max position (per symbol)** | clamp/hard | Clamp qty so |position| ≤ `max_pos_symbol`; REJECT if already over |
| 4 | **Max gross exposure** | clamp/hard | Clamp so Σ|position value| ≤ `max_gross_exposure` × equity |
| 5 | **Max order count / rate** | hard | REJECT beyond `max_orders_per_day` or `max_orders_per_min` (runaway-loop guard) |
| 6 | **Symbol whitelist** | hard | REJECT any symbol not in the configured allowlist |
| 7 | **Stale-data guard** | hard | REJECT if latest data for symbol older than `max_staleness` |
| 8 | **Duplicate-signal guard** | hard | REJECT idempotency-key duplicates within window |
| 9 | **Cash sufficiency** | hard/clamp | REJECT/clamp if fill would breach cash (no leverage in MVP default) |
| 10 | **Sane price/qty** | hard | REJECT non-finite/≤0 qty, price far outside recent range (fat-finger/bad-tick guard) |
| 11 | **Per-strategy budget** | clamp/hard | Cap capital/exposure per strategy so one can't consume the book |
| 12 | **Max drawdown circuit-breaker** | hard | If peak-to-trough equity DD ≥ `max_dd` → auto-KILL + REJECT |

Defaults are **conservative**; every threshold is in config with documented units. Unknown/misconfigured → **fail closed** (REJECT), never fail open.

## 11.4 Sizing hooks (position-sizing models)

Sizing produces the *requested* qty; risk rules 3/4/9/11 then clamp it. MVP sizers:
- **Fixed-fractional:** risk a fixed % of equity per trade (via stop distance).
- **Volatility targeting:** scale size to a target portfolio vol (ATR/rolling-σ based).
- **Fractional Kelly (capped):** only ever a *fraction* of Kelly, hard-capped; never full Kelly. Off by default.

Sizing is deterministic and testable; it never *increases* size past a risk clamp.

## 11.5 State the engine reads

`PortfolioState`: equity, cash, per-symbol positions & marks, realized/unrealized PnL (session + daily), peak equity (for DD), open-order count, per-strategy allocations, last-data-timestamp per symbol, kill flag. Provided by the portfolio/accounting module ([`10`](10-paper-trading-engine-spec.md) §10.7); the engine never mutates it.

## 11.6 Kill switch semantics

- Triggered by: operator (UI/CLI/file flag), daily-loss breach (rule 2, if auto-kill on), max-DD breach (rule 12), reconciliation failure, or repeated data-staleness.
- Effect: `kill_active=true` persisted to disk; REJECT all risk-increasing intents; cancel working orders; optional FLATTEN.
- **Only an explicit operator action clears it.** Never auto-clears on restart or new session.
- Checked at every loop tick and before every order.

## 11.7 Auditability

Every `RiskDecision` (including APPROVEs) is written to the audit log with the rule_hits and the numbers behind them, so any order can be explained after the fact ("why did/didn't this trade?"). Risk state (`RiskStateEvent`) is emitted each bar for the UI's risk panel and the daily report.

## 11.8 Testing (must-haves)

- **Property tests** (hypothesis): no sequence of intents can push |position|, gross exposure, order count, or cash beyond configured limits.
- **Boundary tests:** exactly-at-limit, one-over, clamp-to-limit.
- **Fail-closed tests:** malformed config / missing state → REJECT.
- **Kill tests:** once killed, no risk-increasing order is ever emitted until explicit clear.
- **Choke-point test:** `Order` is only ever constructed after `check()` APPROVE/CLAMP.
- **Determinism:** same intents+state → same decisions.

## 11.9 Configuration (example)

```yaml
risk:
  max_daily_loss: 0.02            # 2% of starting equity
  auto_kill_on_daily_loss: true
  max_dd: 0.10                    # 10% peak-to-trough → auto-kill
  max_pos_symbol: 0.20            # 20% equity per symbol
  max_gross_exposure: 1.00        # no leverage
  max_orders_per_day: 200
  max_orders_per_min: 10
  symbol_whitelist: ["BTC-USDT","ETH-USDT"]
  max_staleness_bars: 3
  cash_only: true                 # no margin in MVP
  per_strategy_budget: 0.50       # each strategy ≤ 50% equity
```

## 11.10 Non-goals (MVP)

No margin/leverage, no options greeks, no portfolio-VaR optimization, no cross-margining. These are *later*. The MVP risk engine is deliberately simple, conservative, and total — a gate that is easy to read, easy to test, and impossible to bypass.

> **Principle:** the risk engine is the most safety-critical code in the system. It is small on purpose, fails closed on purpose, and is tested harder than anything else. See safety review [`14`](14-safety-risk-and-compliance-review.md) and review prompts [`19`](19-claude-code-review-prompts.md).
