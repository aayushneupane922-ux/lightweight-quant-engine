# 05 — Recommended Architecture

**Decision:** Custom lightweight event-driven core (Option 1) with empty-but-defined Hybrid seams (Option 4). One event loop, driven by a pluggable **clock** and **data source**, shared by backtest and paper trading. Every order intent passes through the **risk engine**; nothing can reach a real broker in the MVP.

## 5.1 Design principles

1. **Own the spine, rent the muscles.** You write the event loop, clock, order state machine, portfolio accounting, risk engine, and audit log. Everything else (data, indicators, portfolio math, analytics, UI) is a permissively-licensed library behind an interface.
2. **One strategy interface, two run modes.** A `Strategy` sees the same events whether the clock is a historical replay (backtest) or a wall-clock paper session. This satisfies constraint #7 (shared interfaces) and is the single biggest lever for backtest/paper parity.
3. **Determinism first.** Given the same inputs + config + seed, a run reproduces bit-for-bit. Replay is a first-class feature, not an afterthought (constraint #4/#6).
4. **Risk is a gate, not a suggestion.** The engine cannot emit an order that hasn't passed `RiskEngine.check()`. Enforced by types and a single choke point, not developer discipline.
5. **Live is locked out structurally.** The only `ExecutionAdapter` that exists in MVP is `PaperBroker`. A real broker adapter is *absent from the codebase*, guarded by config + a lockout flag + tests that assert no real-order path exists (constraint #1/#2). See [`10`](10-paper-trading-engine-spec.md), [`14`](14-safety-risk-and-compliance-review.md).
6. **Small and legible.** Target a core a solo dev can read in an afternoon (~2.5–4k lines). Complexity lives in *strategies and research*, not plumbing.

## 5.2 Component diagram (logical)

```
                          ┌───────────────────────────────────────────────┐
                          │                 UI (NiceGUI, localhost)        │
                          │  strategies · experiments · equity · blotter   │
                          │  positions · risk status · KILL SWITCH · logs  │
                          └───────────────▲───────────────┬───────────────┘
                                          │ read state    │ commands (start/stop/kill)
                                          │               ▼
┌──────────────┐   bars/ticks   ┌─────────────────────────────────────────────┐
│ MarketData   │──────────────► │                 EVENT BUS / LOOP             │
│ Adapter      │   MarketEvent  │  (single-threaded, deterministic ordering)   │
│ (ccxt / CSV) │                │                                              │
└──────────────┘                │   Clock (Replay | Wallclock)                 │
                                │      │                                       │
        ┌───────────────────────┘      ▼                                       │
        │                      ┌───────────────┐  SignalEvent  ┌────────────┐  │
        │                      │  Strategy(ies) │──────────────►│  Portfolio │  │
        │                      │  (deterministic│               │ + Sizing   │  │
        │                      │   plugins)     │◄──────────────│            │  │
        │                      └───────────────┘  Fill/Position └─────┬──────┘  │
        │                                                             │ OrderIntent
        │                                                             ▼         │
        │                                                     ┌───────────────┐ │
        │                                                     │  RISK ENGINE  │ │  ← every order
        │                                                     │  (hard gate)  │ │
        │                                                     └──────┬────────┘ │
        │                                                  approved  │  rejected→audit
        │                                                            ▼          │
        │                                                  ┌───────────────────┐│
        │                                                  │ ExecutionAdapter  ││
        │                                                  │  = PaperBroker ONLY││
        │                                                  │ (FillSimulator)   ││
        │                                                  └─────────┬─────────┘│
        │                                                            │ FillEvent │
        └────────────────────────────────────────────────────────────┘         │
                                │                                               │
                                ▼                                               │
      ┌───────────────────────────────────────────┐   append-only   ┌──────────▼───────┐
      │ Storage: Parquet (bars) + DuckDB (queries) │◄───────────────►│  AUDIT LOG (JSONL)│
      │ + run/experiment registry (SQLite/DuckDB)  │                 │  every event/order│
      └───────────────────────────────────────────┘                 └──────────────────┘
```

**Empty-but-defined seams (Option 4, not built in MVP):** `LeanResearchAdapter`, `NautilusExecutionAdapter`, `VectorbtSweepAdapter`, `BrokerExecutionAdapter` — all `NotImplementedError` stubs guarded by the live lockout. Placeholder spec: [`16`](16-mvp-build-plan.md) Milestone 10.

## 5.3 Core interfaces (contract sketch — full schema in [`12`](12-event-and-storage-schema.md))

```python
# Time is injected, never read from the wall clock directly (determinism).
class Clock(Protocol):
    def now(self) -> datetime: ...            # tz-aware UTC
    def advance(self) -> datetime | None: ...  # replay: next event time; wallclock: sleep

class MarketDataAdapter(Protocol):
    def stream(self, symbols: list[str], start=None, end=None) -> Iterator[MarketEvent]: ...
    def capabilities(self) -> DataCapabilities: ...   # bars? ticks? book? delayed?

class Strategy(Protocol):
    name: str; params: dict
    def on_start(self, ctx: Context) -> None: ...
    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]: ...  # PURE-ish, deterministic
    def on_fill(self, ev: FillEvent, ctx: Context) -> None: ...

class Model(Protocol):            # optional signal/analytics plugin (portfolio opt, regime, vol…)
    def fit(self, data) -> "Model": ...
    def predict(self, data): ...

class RiskEngine(Protocol):
    def check(self, intent: OrderIntent, state: PortfolioState) -> RiskDecision: ...  # APPROVE/REJECT/CLAMP

class ExecutionAdapter(Protocol):    # MVP: only PaperBroker implements this
    is_paper: bool                   # MUST be True in MVP; asserted at startup
    def submit(self, order: Order) -> None: ...
    def cancel(self, order_id: str) -> None: ...

class Analytics(Protocol):
    def report(self, run_id: str) -> Report: ...   # wraps QuantStats/empyrical
```

Every third-party dependency hides behind one of these:
- `CcxtMarketDataAdapter`, `CsvReplayAdapter` → `MarketDataAdapter`
- `PandasTaIndicators` (or `TaLibIndicators`) → indicator interface used by strategies
- `SkfolioOptimizer` / `PyPortfolioOptOptimizer` → `Model` (portfolio)
- `QuantStatsAnalytics` → `Analytics`
- `PaperBroker` (owns `FillSimulator`, `SlippageModel`, `CommissionModel`) → `ExecutionAdapter`

## 5.4 Shared backtest ↔ paper pipeline (the key trick)

The *only* differences between a backtest and a paper session are the **Clock** and the **MarketDataAdapter**:

| Concern | Backtest | Paper trading |
|---|---|---|
| Clock | `ReplayClock` (drains historical events as fast as possible) | `WallclockClock` (real time) |
| Data | `CsvReplayAdapter` / historical Parquet | `CcxtMarketDataAdapter` (live public feed) |
| Strategy | same code | same code |
| Risk engine | same code | same code |
| Execution | `PaperBroker` + `FillSimulator` | `PaperBroker` + `FillSimulator` |
| Portfolio/accounting | same code | same code |
| Audit log | same schema | same schema |

Because 90%+ of the code path is identical, "it worked in backtest but paper is different" is reduced to two well-understood surfaces (clock + data), which you test explicitly (see parity tests in [`16`](16-mvp-build-plan.md)).

## 5.5 Concurrency & runtime model

- **Single-threaded, event-ordered core.** Determinism beats throughput for research/paper at this scale. No async in the decision loop.
- **The paper-trading daemon** ([`10`](10-paper-trading-engine-spec.md)) runs the same loop under `WallclockClock`, reading the live adapter, writing audit + state that the UI polls. Network I/O (ccxt) is isolated at the adapter boundary with timeouts and stale-data checks; it never blocks the risk gate logic non-deterministically (bad/late data → *no trade*, logged).
- **UI is a separate process** reading state (DuckDB/SQLite + audit JSONL) and issuing commands (start/stop/**kill**) via a tiny local IPC (file/socket). The UI can crash without touching the engine, and vice-versa.

## 5.6 Technology stack (fixed for MVP)

Python 3.12+ · `ccxt` · `duckdb` + `polars` + `pyarrow` (Parquet) · `pandas`/`numpy` · `pandas-ta` · `QuantStats` · `pydantic` (config/schema validation) · `NiceGUI` (UI) · `pytest` + `hypothesis` (tests) · `ruff`+`mypy` (lint/types) · `structlog` (audit). Later: `skfolio`/`PyPortfolioOpt`, `statsmodels`/`arch`/`hmmlearn`/`ruptures`, `pywebview`/PyTauri (packaging). All MIT/BSD/Apache-2.0 — clean to ship. Rationale + citations: [`02`](02-open-source-framework-matrix.md), [`15`](15-open-source-license-review.md).

## 5.7 Why this is the right call (summary)

It is the **simplest** thing that satisfies **all twelve non-negotiables**, the **cheapest** (only cost is Claude Code), the **most testable** (you own every line), the **most Claude-Code-deterministic** (no framework internals), and it **grows into** the powerful long-term architecture without a rewrite. The trade — you re-implement plumbing that LEAN/Nautilus already have — is exactly the plumbing whose correctness and safety you most need to *control and prove*.
