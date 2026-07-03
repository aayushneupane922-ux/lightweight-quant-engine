# 01 — System Architecture (FINAL)

Local engine + `localhost` web GUI + an autonomous LLM/ML engine room, over a deterministic, audited paper-trading core. Build the spine yourself; consume permissive libraries behind interfaces.

## 1.1 Runtime shape
- **Engine (local process, Python):** the deterministic event core, model runtime, paper broker, risk model, audit log, and the autonomy orchestrator.
- **GUI (browser on `localhost`):** a web UI (served by the engine over `127.0.0.1`) — the "Obsidian Desk" terminal + the 3D neural-web view. No network exposure, no auth.
- **Local LLM (optional, Ollama):** a sidecar the orchestrator calls for reasoning/narration ([`07`](07-cost-stack-and-local-llm.md)).
- **Everything is on your machine. $0/month. No credentials anywhere.**

## 1.2 Component diagram
```
                         ┌───────────────────────────────────────────────┐
   BROWSER (localhost) ─▶ │  GUI: Obsidian Desk terminal + 3D neural-web   │
   ride / observe / tune  │  (reads state, sends whitelisted commands)     │
                         └───────────────▲───────────────┬───────────────┘
                                         │ state (WS)    │ commands: autopilot on/off,
                                         │               │ kill, tune, promote, run-scenario
   ┌──────────────┐  bars/ticks   ┌──────┴───────────────▼───────────────────────────┐
   │ MarketData   │──────────────▶│                LOCAL ENGINE                        │
   │ Adapter      │  MarketEvent  │                                                    │
   │ (ccxt/CSV)   │               │  ┌───────────────── AUTONOMY ORCHESTRATOR ───────┐ │
   └──────────────┘               │  │  LLM (plans/interprets/narrates)              │ │
                                  │  │   + HPO engine (Optuna: the real search)      │ │
                                  │  │   + drift monitor (River)                     │ │
                                  │  │   → proposes configs → SANDBOX tests →         │ │
                                  │  │     VALIDATION gate → promote to tracked book │ │
                                  │  └───────┬───────────────────────┬───────────────┘ │
                                  │          │ chosen configs        │ experiments      │
                                  │          ▼                       ▼ (sandbox)        │
                                  │   ┌──────────────┐        ┌──────────────┐          │
                                  │   │ MODEL RUNTIME│  N live│ MODEL RUNTIME│          │
                                  │   │ (tracked book)│ models │ (sandbox)    │          │
                                  │   └──────┬───────┘        └──────┬───────┘          │
                                  │          │ SignalEvent           │                  │
                                  │          ▼                       ▼                  │
                                  │      make_order ▶ RISK MODEL ▶ PaperBroker (sim)    │
                                  │          │ every event                              │
                                  │          ▼                                          │
                                  │  hash-chained AUDIT (jsonl) + DuckDB  ◀── replay ── │
                                  │          │                                          │
                                  │          ▼  StateReader (read-only) ─▶ GUI          │
                                  └────────────────────────────────────────────────────┘
```

## 1.3 Layers & interfaces (own the spine, rent the muscles)
You write: event loop, clock, order state machine, portfolio/cash accounting, risk model, audit/hash-chain, paper broker, and the autonomy orchestrator's control flow. Behind interfaces (permissive libs): `ccxt` (data), DuckDB/Polars/PyArrow/Parquet (storage), pandas-ta/statsmodels/arch/hmmlearn/ruptures/skfolio/PyPortfolioOpt/riskfolio (models), scikit-learn/LightGBM/River/**Optuna** (learning loop), Ollama (LLM), three.js/`3d-force-graph` (3D viz).

Core Protocols (in `core/`): `Clock`, `MarketDataAdapter`, `Strategy`, `Model`, `RiskModel`, `ExecutionAdapter` (paper only), `Analytics`, and new: `Orchestrator`, `Optimizer`, `Validator`, `PromotionGate`, `Narrator` (LLM). Contracts in [`06`](06-engine-data-risk-and-audit.md).

## 1.4 Determinism with a stochastic LLM in the loop (the key trick)
LLMs are non-deterministic; the system stays reproducible anyway because:
- **Execution is deterministic:** given a config (models+params+seed) and a data slice, a sim run reproduces bit-for-bit.
- **The LLM's *actions are recorded*, not re-derived:** every proposal, chosen config, tune, promotion, and its prompt+response are written to the audit log. A session **replays from the logged actions**, so the whole run is reproducible even though re-invoking the LLM might differ.
- **The judge is deterministic:** Optuna trials + walk-forward validation are seeded and reproducible; the LLM decides *what* to try, deterministic code decides *what's real*.

Result: an autonomous, aggressive, LLM-driven system that is still fully **auditable and replayable** — non-negotiable #2.

## 1.5 Two surfaces (sandbox vs tracked book)
- **Sandbox model runtime:** aggressive, unvalidated exploration on historical/held-out data + a shadow live feed. The LLM/HPO loop lives here.
- **Tracked model runtime:** the live paper book you watch; accepts only promoted (validated) configs; de-risks on degradation. Same code path; different governance.

## 1.6 Concurrency
Single-threaded, event-ordered **decision** loop per book (determinism). The orchestrator runs experiments as separate seeded sim jobs (parallelizable) that never mutate the tracked book directly — they emit *promotion candidates* the gate accepts or rejects. Network I/O (ccxt, Ollama) is isolated at adapter boundaries with timeouts; bad/late data ⇒ no trade, logged.

## 1.7 Tech stack (final, all permissive/local)
Python 3.12+ · ccxt · duckdb+polars+pyarrow · pandas/numpy · pandas-ta · statsmodels/arch/hmmlearn/ruptures · skfolio/PyPortfolioOpt/riskfolio-lib · scikit-learn/LightGBM/River/**Optuna** · pydantic · FastAPI+NiceGUI (localhost GUI) · three.js + `3d-force-graph` (3D) · Ollama (optional local LLM) · pytest+hypothesis · ruff+mypy · structlog. Licenses/rationale: [`archive/02-open-source-framework-matrix.md`](archive/02-open-source-framework-matrix.md), [`archive/15-open-source-license-review.md`](archive/15-open-source-license-review.md); local-LLM in [`07`](07-cost-stack-and-local-llm.md).
