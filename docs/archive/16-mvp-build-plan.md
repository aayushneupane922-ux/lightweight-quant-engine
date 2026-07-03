# 16 — MVP Build Plan (for Claude Code)

The implementation blueprint. Pair with the master prompt [`17`](17-claude-code-master-prompt.md), milestone prompts [`18`](18-claude-code-milestone-prompts.md), and review prompts [`19`](19-claude-code-review-prompts.md).

## 16.1 Repo structure

```
lightweight-quant-engine/
├── CLAUDE.md                      # agent context (see §16.9)
├── pyproject.toml                 # deps, ruff, mypy, pytest config
├── README.md
├── THIRD_PARTY_NOTICES.md
├── config/
│   ├── engine.example.yaml
│   └── risk.example.yaml
├── src/lqe/
│   ├── core/                      # OWNED: event loop, clock, bus, ids, hashing
│   │   ├── events.py  clock.py  bus.py  engine.py  context.py  determinism.py
│   ├── data/                      # MarketDataAdapter impls + ingestion + validation
│   │   ├── base.py  ccxt_adapter.py  csv_replay.py  ingest.py  validate.py  symbols.py
│   ├── storage/                   # Parquet + DuckDB catalog + replay bundles
│   │   ├── parquet.py  catalog.py  replay_bundle.py
│   ├── strategies/                # deterministic strategy plugins
│   │   ├── base.py  trend_ma_cross.py  mean_reversion_z.py  ts_momentum.py
│   ├── models/                    # optional Model plugins (later milestones)
│   │   └── base.py
│   ├── portfolio/                 # accounting + sizing
│   │   ├── accounting.py  sizing.py
│   ├── risk/                      # THE risk gate (safety-critical)
│   │   └── engine.py  rules.py
│   ├── execution/                 # PaperBroker ONLY (+ stubbed lockout)
│   │   ├── base.py  paper_broker.py  fills.py  slippage.py  commission.py
│   │   └── _locked_out.py         # NotImplementedError stubs behind LIVE_TRADING_ENABLED=False
│   ├── analytics/                 # QuantStats/empyrical wrappers
│   │   └── report.py  metrics.py
│   ├── backtest/                  # run orchestration (replay clock)
│   │   └── runner.py
│   ├── paper/                     # paper-trading daemon (wallclock)
│   │   └── daemon.py  control.py  kill_switch.py
│   ├── ui/                        # NiceGUI app (separate process)
│   │   └── app.py  views/*.py
│   └── cli.py                     # `lqe ingest|backtest|paper|report`
├── tests/
│   ├── unit/  integration/  property/  parity/  safety/
└── research/
    ├── journal/                   # H-YYYYMMDD-nn.md hypothesis logs
    └── notebooks/
```

## 16.2 Technology stack (fixed)

Python 3.12+ · ccxt · duckdb + polars + pyarrow · pandas + numpy · pandas-ta · quantstats · pydantic · NiceGUI · pytest + hypothesis · ruff + mypy · structlog. Later: skfolio/PyPortfolioOpt, statsmodels/arch/hmmlearn/ruptures, pywebview/PyTauri. (Licenses/rationale: [`02`](02-open-source-framework-matrix.md), [`15`](15-open-source-license-review.md).)

## 16.3 Module boundaries (dependency direction)

`core` depends on nothing project-specific. `data`, `storage`, `strategies`, `risk`, `execution`, `portfolio`, `analytics` depend on `core` (events/interfaces) only. `backtest`/`paper` orchestrate. `ui` depends on `storage`+`paper.control` (read state, send control) — **never** on `execution`/`risk` internals. Third-party libs sit behind adapter modules; no library type leaks past its adapter.

## 16.4 Interface definitions

All in `core` (Protocols) and realized per §16.1: `Clock`, `MarketDataAdapter`, `Strategy`, `Model`, `RiskEngine`, `ExecutionAdapter`, `Analytics`. Contracts: [`05`](05-recommended-architecture.md) §5.3, [`12`](12-event-and-storage-schema.md).

## 16.5 Milestone plan (10 milestones)

| # | Milestone | Delivers | Depends on |
|---|---|---|---|
| 1 | **Local-only core engine** | events, clock, bus, deterministic loop, config, **live lockout**, hashing | — |
| 2 | **Data ingestion & validation** | ccxt + csv adapters, Parquet store, DuckDB catalog, quality checks, symbol registry | 1 |
| 3 | **Backtesting / replay** | replay bundles, backtest runner, PaperBroker + fills/slippage/commission, accounting | 1,2 |
| 4 | **Research analytics** | QuantStats metrics/tearsheets, experiment registry, cost-sensitivity sweep | 3 |
| 5 | **Paper broker hardening** | order state machine, reconciliation, stale/duplicate guards, audit hash-chain | 3 |
| 6 | **Lightweight UI** | NiceGUI: strategies/experiments/equity/blotter/positions/risk/**kill**/data-health | 4,5 |
| 7 | **Model-library integration** | Model plugin interface + first optional model (e.g., vol filter/sizer) behind interface | 4 |
| 8 | **Paper-trading daemon** | wallclock daemon, kill switch, daily report, control IPC | 5,6 |
| 9 | **Safety & audit review** | lockout tests, risk property tests, parity tests, reconciliation, license CI gate | all |
| 10 | **Future adapter spike (placeholder)** | empty `NautilusExecutionAdapter`/`BrokerExecutionAdapter` stubs + design notes (NO Sierra research) | 9 |

**Sequencing note:** implement **Milestone 1 and the Milestone-9 lockout/risk tests early** (before strategies) — prove the system is safe and deterministic before it can do anything.

## 16.6 Acceptance criteria (per milestone — abbreviated; full in [`18`](18-claude-code-milestone-prompts.md))

- **M1:** deterministic loop passes replay-equality test; config rejects `mode: live`; `is_paper` assertion enforced; `LIVE_TRADING_ENABLED=False` constant present; ruff+mypy clean.
- **M2:** ingest BTC-USDT/ETH-USDT to Parquet; all §8.4 checks run and fail loudly on injected bad data; symbol registry maps native↔canonical; data versioned in catalog.
- **M3:** a trivial strategy backtests end-to-end; fills are next-bar/pessimistic; accounting reconciles; two identical runs produce identical audit hashes.
- **M4:** QuantStats tearsheet generated; experiment registry populated; cost-sensitivity sweep (0/5/10/20 bps) produced.
- **M5:** order state machine enforces legal transitions; reconciliation halts on injected mismatch; stale/duplicate guards reject appropriately; audit hash-chain verifies.
- **M6:** UI shows all required views; kill button flips `kill_active` and blocks new orders; nothing bound beyond 127.0.0.1.
- **M7:** one Model plugin works behind the interface and is ablation-tested (proves it helps or is removed).
- **M8:** daemon runs a paper session on live ccxt data; kill switch works from UI+file; daily report generated; rebuild-from-audit on restart reconciles.
- **M9:** all safety tests green (see [`19`](19-claude-code-review-prompts.md)); license CI gate blocks copyleft/Commons-Clause in runtime deps.
- **M10:** stubs raise `NotImplementedError` behind the lockout; design notes present; **no Sierra/DTC research performed**.

## 16.7 What NOT to build yet (guardrails against scope creep)

- ❌ Any real broker adapter, live mode, or credential handling.
- ❌ Sierra Chart / DTC anything (only generic seams).
- ❌ Cloud deployment, multi-user, remote UI, auth.
- ❌ RL/LLM decision models; deep learning.
- ❌ Options, order-book microstructure, HFT.
- ❌ Cross-sectional factor universes / equities data pipeline.
- ❌ Portfolio-optimization layer (defer to post-MVP; MVP sizing = fixed-fractional/vol-target).
- ❌ Fancy charts/React front end; DB-backed UI.

## 16.8 Safety gates (must hold at every milestone)

1. `execution_adapter.is_paper is True` asserted at startup.
2. Config schema has **no** live/real-broker enum values.
3. No broker SDK import; no `ccxt` order-creation call anywhere in the engine.
4. Only one function constructs `Order`, after the risk gate.
5. Kill switch reachable and effective; never auto-clears.
6. Every order intent audited; audit hash-chain verifies.
7. Deterministic replay equality holds.
8. License CI gate green.

## 16.9 Suggested `CLAUDE.md` (project context for the agent)

```markdown
# lightweight-quant-engine — agent context

## What this is
A local-first, paper-trading-only quant research engine. Crypto-first, asset-agnostic
via adapters. NO live trading in the MVP. Determinism, auditability, and a hard risk
gate are non-negotiable.

## Absolute rules (never violate)
1. No live trading. No broker credentials. No real-order code paths. Ever, in MVP.
2. Every OrderIntent MUST pass RiskEngine.check() via the single choke point.
3. Strategies are deterministic: no wall-clock reads, no unseeded RNG, no network.
4. The only ExecutionAdapter is PaperBroker (is_paper=True, asserted at startup).
5. Config schema must reject mode: live / real execution adapters.
6. Every event is appended to the hash-chained audit log.
7. Do NOT research or reference Sierra Chart / DTC. Use generic adapter seams only.
8. Runtime deps must be MIT/BSD/Apache-2.0 (no GPL/Commons-Clause). vectorbt = research only.

## Conventions
- UTC tz-aware timestamps; bars are left-edge; act on a bar only after it completes.
- Money/qty precision explicit; no silent float drift in accounting.
- Behind-interface only: no third-party type leaks past its adapter module.
- Tests: unit + property (hypothesis) + parity (backtest↔paper) + safety (lockout).

## Definition of done (any change)
ruff + mypy clean; tests green incl. safety + determinism; audit intact; docs updated.

## Where to look
Specs live in /docs (00–23). Read 05 (architecture), 10/11 (paper/risk), 12 (schema),
09 (research protocol) before implementing. When unsure, prefer the smaller, safer option.
```

## 16.10 Suggested Claude Code subagents

- **`safety-reviewer`** — audits every diff against §16.8 gates and [`19`](19-claude-code-review-prompts.md); has veto power on merges touching `risk/`, `execution/`, `paper/`.
- **`test-author`** — writes property/parity/safety tests for each new module before/with implementation.
- **`data-quality`** — implements/extends §8.4 checks and generates data-validation reports.
- **`license-auditor`** — runs `pip-licenses`, flags any copyleft/Commons-Clause in runtime deps.
- **`research-methodologist`** — enforces the [`09`](09-backtesting-research-protocol.md) protocol on any strategy work (DSR/PBO/kill-criteria).

## 16.11 Suggested Claude Code skills (project-local)

- **`add-strategy`** — scaffold a deterministic strategy plugin + manifest + hypothesis journal entry + tests.
- **`run-backtest`** — build replay bundle, run, register experiment, emit tearsheet + cost-sensitivity.
- **`safety-check`** — run the full safety/lockout/determinism suite and print a pass/fail gate report.
- **`ingest-crypto`** — pull ccxt history for symbols/timeframes, validate, version into catalog.
- **`new-hypothesis`** — create a `research/journal/H-*.md` from the §9.1 template.

## 16.12 Test plan (coverage targets)

- **Unit:** events, clock, accounting, fills, each risk rule, each strategy.
- **Property (hypothesis):** risk invariants (no breach possible); accounting conservation (cash+positions == equity); state-machine legality.
- **Parity:** replay a paper session through the backtester → identical decisions.
- **Determinism:** two identical runs → identical audit hashes.
- **Safety:** lockout suite ([`19`](19-claude-code-review-prompts.md)) — no live path, `is_paper` enforced, no broker imports, kill switch effective.
- **Data:** injected-bad-data tests for every §8.4 check.
- CI runs all + ruff + mypy + license gate on every commit.
