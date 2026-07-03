# 06 — Engine, Data, Risk & Audit (FINAL, consolidated)

The deterministic core, data layer, (sim) risk model, and the audit/replay backbone. Deep versions preserved in [`archive/`](archive/) (08 data, 10 paper engine, 11 risk, 12 schema, 14 safety).

## 6.1 Event core & interfaces
Single-threaded, event-ordered decision loop driven by an injected `Clock` (`ReplayClock` for backtests/replay, `WallclockClock` for the live sim). Same loop runs sandbox and tracked books. Core Protocols: `Clock`, `MarketDataAdapter`, `Strategy`, `Model`, `RiskModel`, `ExecutionAdapter` (paper only), `Analytics`, `Orchestrator`, `Optimizer`, `Validator`, `PromotionGate`, `Narrator`. One choke point `make_order(intent, risk_decision)` constructs every `Order`, after the risk model.

## 6.2 Event & storage schema (essentials)
Events (immutable, hash-chained envelope): `MarketEvent, SignalEvent, OrderIntent, RiskDecision, Order, FillEvent, PositionEvent, RiskStateEvent, ControlEvent` + autonomy events: `HypothesisEvent, TrialEvent, ValidationEvent, PromotionEvent, DeRiskEvent, NarrationEvent`. Each carries `run_id, seq, sim_ts, wall_ts, prev_hash, hash`. Storage: partitioned **Parquet** (bars) + **DuckDB** catalog (data versions, symbols, experiments/trials, audit mirror, daily reports). Money/qty `Decimal`; UTC left-edge bars; canonical `BASE-QUOTE` symbols. Full field-level schema: [`archive/12-event-and-storage-schema.md`](archive/12-event-and-storage-schema.md).

## 6.3 Data strategy (crypto-first, agnostic)
Free crypto public data via `ccxt` (no key) → validate (gaps, OHLC sanity, outliers, dupes, survivorship-safe symbols) → curated Parquet → versioned in the catalog → frozen **replay bundles** for reproducible backtests/trials. Bad/late data ⇒ no trade, logged. Equities/futures plug in later via adapters. Details: [`archive/08-data-strategy.md`](archive/08-data-strategy.md).

## 6.4 The (simulated) risk model
The risk model is the single gate before `make_order`; in this sim-first product it serves **research integrity + realistic fills**, and — per the owner's decision — the autopilot may **tune** its parameters aggressively. It still runs on every order (so sims are meaningful and auditable):
- Per-order checks: sane price/qty, cash/position accounting, stale-data guard, duplicate-signal guard, symbol whitelist.
- Book-level: exposure, drawdown, per-model/per-strategy budgets, order-rate cap (runaway-loop guard). These are **tunable by the autopilot in the sim** (not fixed safety limits), but every value + breach is audited.
- **De-risk action** (degradation response, [`02`](02-autonomy-autopilot-and-learning-loop.md) §2.4): cut exposure / pause a model / retire it.
- **Human KILL/freeze:** persistent, disk-backed, halts autonomy + optionally flattens the sim book; **only the human clears it**; the LLM cannot disable it.

## 6.5 Audit, determinism & replay (integrity backbone)
Append-only JSONL, hash-chained (each record hashes the prior), mirrored to DuckDB. Records every event **and every autonomy action** (hypotheses, trials, validations, promotions, de-risks, LLM prompt+response). Execution is deterministic per config+seed; LLM stochasticity is captured by **logging its actions**, so a whole autonomous session **replays exactly from the log** (and drives the 3D timeline scrubber). Reconciliation each bar + on restart (rebuild-from-audit). This is non-negotiable #2 — it's what makes the aggressive autonomy honest and debuggable.

## 6.6 Paper-only lockout (the one hard safety rail)
The only `ExecutionAdapter` is `PaperBroker` (`is_paper=True`, asserted at startup). No broker SDK, no credentials, no `ccxt` order calls anywhere; config schema rejects any live mode; `LIVE_TRADING_ENABLED=False` with no supported flip. Future real-execution adapters exist only as guarded `NotImplementedError` stubs. Enforced by `tests/safety/`. Details: [`archive/14-safety-risk-and-compliance-review.md`](archive/14-safety-risk-and-compliance-review.md).

## 6.7 Acceptance criteria
- Deterministic loop; one `make_order` choke point after the risk model; two books (sandbox/tracked) on the same code path.
- Full event+autonomy audit, hash-chain verifies, session replays from the log, reconciliation holds.
- Data validated + versioned; replay bundles reproducible; bad data ⇒ no trade.
- Paper-only lockout tests green; human kill un-overridable by the LLM.
