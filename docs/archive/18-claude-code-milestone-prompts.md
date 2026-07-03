# 18 — Claude Code Milestone Prompts

Run these **one at a time**, after the master prompt ([`17`](17-claude-code-master-prompt.md)). Each ends with "STOP for review." Copy the block verbatim.

---

## Milestone 1 — Local-only core engine (do this FIRST)

```
Implement Milestone 1: the deterministic core engine + safety lockout. NO strategies,
NO data yet beyond a synthetic event source for tests.

Build in src/lqe/core:
- events.py: immutable pydantic event models (envelope + MarketEvent, SignalEvent,
  OrderIntent, RiskDecision, Order, FillEvent, RejectEvent, PositionEvent,
  RiskStateEvent, ControlEvent) exactly per docs/12.
- clock.py: Clock Protocol + ReplayClock (drains a time-ordered iterable) and
  WallclockClock (real time). Time is always injected; never read the wall clock elsewhere.
- bus.py: single-threaded, deterministic event bus with monotonic seq.
- engine.py: the loop: pull event -> dispatch -> collect emitted events -> order by
  (sim_ts, seq). Deterministic given inputs+seed.
- determinism.py: canonical JSON + sha256 hash-chain helpers for the audit log.
- context.py: Context object (read-only market/history access, positions/equity, params,
  logger). Strategies cannot submit orders; they only return SignalEvents.
- config: pydantic models; engine.mode Enum = {backtest, paper} ONLY (NO live);
  execution.adapter Enum = {paper} ONLY. LIVE_TRADING_ENABLED=False constant in a
  constants module. Startup validation raises if these are violated.
- A single choke-point function make_order(intent, risk_decision) that is the ONLY place
  an Order is constructed.

Tests (tests/unit, tests/property, tests/safety):
- replay-equality: two runs over the same synthetic events + seed produce identical
  audit hashes.
- config rejects mode: live and non-paper execution adapters.
- make_order is the only constructor of Order (assert via AST/grep test).
- hash-chain verifies over a synthetic run.
Tooling: pyproject with ruff+mypy+pytest; make everything type-clean.

Acceptance: all above tests green; ruff+mypy clean. Then STOP and summarize for review.
```

---

## Milestone 2 — Data ingestion & validation

```
Implement Milestone 2: crypto data ingestion, validation, storage. Per docs/08.

- data/base.py: MarketDataAdapter Protocol + DataCapabilities.
- data/ccxt_adapter.py: CcxtMarketDataAdapter using ccxt PUBLIC endpoints only
  (fetch_ohlcv, watch/stream). Rate-limit aware, paginated, idempotent. NO trading calls
  (no create_order etc.) anywhere.
- data/csv_replay.py: CsvReplayAdapter for deterministic local files.
- data/symbols.py: canonical symbol registry (native<->canonical), survivorship-safe
  (keep delisted), stored in catalog.
- storage/parquet.py + storage/catalog.py: partitioned Parquet writer + DuckDB catalog
  (data_versions, symbols tables per docs/12).
- data/validate.py: ALL docs/08 §8.4 checks (monotonic/unique ts, OHLC sanity, volume,
  gap report, outliers, checksum+manifest). Fail loudly; quarantine bad data.
- data/ingest.py + cli `lqe ingest`: fetch -> raw Parquet+manifest -> validate ->
  normalize -> curated -> register version.

Tests: inject bad data (dupe ts, high<low, negative price, gaps) and assert each check
fires; assert canonical mapping; assert ingestion idempotency; assert no ccxt trading
method is importable/used in the codebase (safety test).

Acceptance: ingest BTC-USDT and ETH-USDT 1m/1h to curated Parquet; catalog populated;
all validation tests green. STOP for review.
```

---

## Milestone 3 — Backtesting / replay

```
Implement Milestone 3: end-to-end backtest with a trivial strategy. Per docs/03, 05, 10.

- storage/replay_bundle.py: build/load frozen, checksummed replay bundles (docs/08 §8.5).
- execution/base.py: ExecutionAdapter Protocol (is_paper).
- execution/paper_broker.py: PaperBroker (is_paper=True) with order state machine
  (docs/10 §10.4).
- execution/fills.py, slippage.py, commission.py: pessimistic FillSimulator (next-bar-open
  default), SlippageModel (fixed_bps default), CommissionModel (bps). Same objects used in
  backtest and paper.
- portfolio/accounting.py: position/cash/portfolio accounting, mark-to-market, equity curve.
- portfolio/sizing.py: fixed-fractional + vol-target sizers.
- strategies/base.py + strategies/trend_ma_cross.py: one trivial deterministic strategy.
- backtest/runner.py + cli `lqe backtest`: run a bundle through the loop, write audit.

Tests: end-to-end backtest produces trades + equity curve; accounting reconciles
(cash+positions==equity); two identical runs => identical audit hashes; fills never use
future data (bar-completeness test).

Acceptance: `lqe backtest` runs on a real crypto bundle deterministically. STOP for review.
```

---

## Milestone 4 — Research analytics

```
Implement Milestone 4: analytics + experiment registry. Per docs/09.

- analytics/metrics.py + report.py: wrap QuantStats/empyrical behind an Analytics
  interface; produce a tearsheet (Sharpe, Sortino, maxDD+duration, Calmar, turnover,
  hit rate, tail ratio, n_trades) as markdown/HTML.
- storage/catalog.py: experiments table (docs/12); register every run with provenance
  (git sha, config hash, data version, seed) and metrics.
- backtest/runner.py: add a cost-sensitivity sweep (0/5/10/20 bps) and a
  parameter-sweep helper that records a plateau/spike heatmap.
- Optional: Deflated Sharpe Ratio + a simple PBO estimate helper (docs/09 §9.7).

Tests: tearsheet generated; registry row written with full provenance; cost sweep output
present; DSR helper returns sane values on known inputs.

Acceptance: a backtest yields a tearsheet + a registry entry + a cost-sensitivity table.
STOP for review.
```

---

## Milestone 5 — Paper broker hardening

```
Implement Milestone 5: make the simulated broker + accounting production-grade. Per docs/10, 11.

- Finish order state machine (illegal transitions raise + audit).
- risk/engine.py + risk/rules.py: implement ALL MVP risk rules (docs/11 §11.3) with
  APPROVE/CLAMP/REJECT, fail-closed, config-driven. Wire as the single gate before make_order.
- paper/kill_switch.py: persistent kill flag (disk), checked every tick + before every
  order; never auto-clears.
- reconciliation: each bar + on shutdown, independently recompute equity and assert match;
  halt on mismatch.
- stale-data + duplicate-signal guards (docs/10 §10.9).
- audit hash-chain end-to-end; rebuild-from-audit on restart + reconcile.

Tests (property + safety): no intent sequence can breach any limit; kill => no
risk-increasing order ever; reconciliation halts on injected mismatch; stale/duplicate
guards reject; hash-chain verifies; rebuild-from-audit reproduces state.

Acceptance: risk gate + kill + reconciliation all enforced and tested. STOP for review.
```

---

## Milestone 6 — Lightweight UI

```
Implement Milestone 6: the NiceGUI local desktop UI (localhost only). Per docs/13.

- ui/app.py + ui/views/*: strategy list, experiment list, backtest runs (equity +
  drawdown charts, trade blotter, tearsheet), positions, orders, event-log viewer, risk
  status, paper-trading status, data health, configuration viewer (showing
  "Mode: PAPER · Live trading: LOCKED"), daily report, strategy/model comparison,
  parameter-sweep results.
- Big, obvious KILL button (+ FLATTEN) that flips the persistent kill flag via the control
  IPC. UI reads state from DuckDB + audit JSONL; sends ONLY whitelisted control commands.
- Bind to 127.0.0.1 only. UI cannot construct orders or import risk/execution internals.

Tests: UI process starts; kill button flips kill flag and blocks new orders; assert UI
sends only whitelisted commands; assert no bind beyond localhost.

Acceptance: all required views render from local data; kill works from the UI. STOP for review.
```

---

## Milestone 7 — Model-library integration

```
Implement Milestone 7: the Model plugin interface + ONE optional model, behind an interface.
Per docs/03, 12.

- models/base.py: Model Protocol (fit/predict/save/load), deterministic given fitted params.
- Implement ONE optional model as a FILTER/SIZER input only (e.g., an arch-based vol
  estimator feeding vol-targeting, OR a trivial ruptures/vol regime on/off filter).
  It must NOT make autonomous trades; it feeds a deterministic strategy/sizer.
- Ablation harness: run the strategy WITH and WITHOUT the model; report whether it helps.
  If it doesn't clearly help, mark it optional/off by default (docs/09 §9.7).

Tests: model is deterministic; ablation report produced; strategy still deterministic and
passes replay-equality with the model enabled.

Acceptance: one model plugin integrated + ablation-tested behind the interface. STOP for review.
```

---

## Milestone 8 — Paper-trading daemon

```
Implement Milestone 8: the live-clock paper daemon. Per docs/10.

- paper/daemon.py: run the SAME loop under WallclockClock reading CcxtMarketDataAdapter
  live public feed; PaperBroker fills; risk gate; audit; state for the UI.
- paper/control.py: local IPC (127.0.0.1 socket or file flag) for START/STOP/KILL/FLATTEN.
- Daily report generation at session boundary + on demand (docs/10 §10.13).
- Network isolation: adapter timeouts; bad/late data => no trade (stale guard), logged;
  network variability must not leak into decisions (still deterministic given recorded data).
- Restart safety: rebuild-from-audit + reconcile before accepting new signals.

Tests: run a short live paper session (or a simulated wallclock feed); kill from UI+file
works; daily report generated; parity test (replay the session's recorded data through the
backtester => identical decisions).

Acceptance: a paper session runs on live crypto data with kill + daily report + parity.
STOP for review.
```

---

## Milestone 9 — Safety & audit review

```
Implement Milestone 9: complete the safety/audit suite and CI gates. Per docs/14, 16, 19.

- tests/safety: assert NO real-order path exists — only PaperBroker implements
  ExecutionAdapter; is_paper enforced at startup; no broker SDK import; no ccxt
  order-creation call anywhere; config schema rejects live; UI sends only whitelisted commands.
- Full risk property-test sweep; reconciliation + kill tests; determinism/parity tests.
- CI: add `pip-licenses` gate that FAILS the build if any runtime dependency is GPL or
  carries Commons Clause. ruff+mypy+pytest all required.
- Generate a THIRD_PARTY_NOTICES file from installed licenses.

Acceptance: every safety gate in docs/16 §16.8 is enforced by a green test; license gate
active. STOP for review.
```

---

## Milestone 10 — Future adapter spike (placeholder; NO Sierra research)

```
Implement Milestone 10: empty, guarded seams for the future — WITHOUT researching or
implementing Sierra Chart / DTC or any real broker.

- execution/_locked_out.py: NautilusExecutionAdapter, BrokerExecutionAdapter stubs that
  raise NotImplementedError and are unreachable while LIVE_TRADING_ENABLED=False.
- data: a generic ExternalMarketDataAdapter stub (docstring notes it's where a future
  vendor/Sierra/broker feed would attach) — no implementation.
- docs/adapters-future.md: short design notes on the seam contracts ONLY. Explicitly write
  "Sierra Chart / DTC to be researched separately later — not in scope here."

Tests: importing/instantiating the stubs raises NotImplementedError; lockout still holds;
all prior safety tests still green.

Acceptance: seams exist as guarded stubs with design notes; no live capability introduced;
no Sierra/DTC content. STOP for review.
```

---

**After Milestone 10:** the MVP is complete — a deterministic, auditable, paper-only research + paper-trading engine on free crypto data, with a local desktop UI, a hard risk gate, and a clean upgrade path. Do not proceed to any live-trading work without the professional-review gates in [`14`](14-safety-risk-and-compliance-review.md).
