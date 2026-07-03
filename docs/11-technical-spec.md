# 11 — Detailed Technical Specification

Implementation-level contracts for `lightweight-quant-engine`. An engineer should be able to implement each module from this without re-deriving design. Complements: [`01`](01-system-architecture.md) (architecture), [`02`](02-autonomy-autopilot-and-learning-loop.md) (autonomy), [`04`](04-validation-and-overfitting-protocol.md) (gate), [`06`](06-engine-data-risk-and-audit.md) (engine/data/risk/audit), [`10`](10-production-roadmap.md) (build order). Signatures are Python 3.12 (`typing.Protocol`, pydantic v2). Where this doc and code disagree, **the tests in `tests/safety` and `tests/honesty` win.**

## 11.0 Conventions
- **Types:** `Symbol = str` (canonical `BASE-QUOTE`, upper); `Timeframe = Literal["1m","5m","15m","1h","4h","1d"]`; `Price/Qty = decimal.Decimal`; `Bps = float`; `RunId/EventId/TrialId = str` (uuid4); timestamps `datetime` tz-aware **UTC**, bars **left-edge**.
- **Determinism:** no wall-clock reads outside `Clock`; no unseeded RNG; no network/IO in a decision path; dict-order never load-bearing.
- **Money:** `Decimal` throughout accounting; explicit rounding at market precision; never float-drift.
- **Errors:** typed exceptions in `core/errors.py` (`ConfigError, DataQualityError, RiskRejected, ReconciliationError, GateError, LockoutViolation`). Fail **closed**.

## 11.1 Module map & import rules
```
core/      → depends on nothing project-specific   (events, clock, bus, engine, context, determinism, make_order, config, types, errors, constants)
data/      → core                                  (base, ccxt_adapter, csv_replay, ingest, validate, symbols)
storage/   → core                                  (parquet, catalog, replay_bundle, state_reader)
models/    → core                                  (base, adapters/*, plugins/*)
portfolio/ → core                                  (accounting, sizing)
risk/      → core, portfolio                        (model, rules, kill_switch)
execution/ → core, portfolio, risk                  (base, paper_broker, fills, slippage, commission, _locked_out)
analytics/ → core, storage                          (metrics, dsr, pbo, tearsheet, registry)
backtest/  → core, data, storage, models, portfolio, risk, execution, analytics  (make_session, runner)
autonomy/  → backtest, analytics, models, risk       (orchestrator, optimizer, validator, promotion_gate, drift, narrator, books)
live/      → autonomy, execution, data              (sandbox_book, tracked_book, daemon, control)
ui/        → storage(state_reader), live(control)    (app, views/*, theme/*)  — NEVER imports risk/execution/autonomy internals
viz3d/     → storage(state_reader)                   (neural_web, payload)
cli/       → backtest, live, data, analytics
```
**Rule:** a lower layer never imports a higher one; third-party libs never leak past their adapter module; `ui`/`viz3d` are read-only + control-command only.

## 11.2 Core interfaces (Protocols — full signatures)
```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def advance(self) -> datetime | None: ...          # replay: next event ts; wallclock: sleep→now

class MarketDataAdapter(Protocol):
    def capabilities(self) -> DataCapabilities: ...     # bars?/ticks?/book?/delayed?
    def stream(self, symbols: list[Symbol], tf: Timeframe,
               start: datetime | None = None, end: datetime | None = None) -> Iterator[MarketEvent]: ...
    # MUST NOT expose create_order/cancel_order/withdraw or any trading method.

class Strategy(Protocol):
    name: str; params: dict
    def on_start(self, ctx: "Context") -> None: ...
    def on_market(self, ev: MarketEvent, ctx: "Context") -> list[SignalEvent]: ...   # deterministic, causal
    def on_fill(self, ev: FillEvent, ctx: "Context") -> None: ...

class Model(Protocol):                                  # optional signal/alloc/regime plugin
    name: str
    def fit(self, data: "TrainView") -> "Model": ...     # offline; returns fitted (frozen) instance
    def predict(self, data: "FeatureView") -> "ModelOutput": ...   # deterministic given fitted params
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> "Model": ...

class RiskModel(Protocol):
    def check(self, intent: OrderIntent, state: PortfolioState) -> RiskDecision: ...  # APPROVE/CLAMP/REJECT
    def on_bar(self, state: PortfolioState) -> RiskStateEvent: ...
    @property
    def kill_active(self) -> bool: ...

class ExecutionAdapter(Protocol):
    is_paper: bool                                       # MVP invariant: True, asserted at startup
    def submit(self, order: Order) -> None: ...
    def cancel(self, order_id: str) -> None: ...
    def working_orders(self) -> list[Order]: ...

class Analytics(Protocol):
    def metrics(self, run_id: RunId) -> Metrics: ...
    def tearsheet(self, run_id: RunId) -> Report: ...

class Optimizer(Protocol):                               # Optuna wrapper
    def study(self, space: SearchSpace, objective: "TrialObjective",
              n_trials: int, seed: int) -> StudyResult: ...

class Validator(Protocol):
    def validate(self, candidate: "PromotionCandidate") -> "ValidationResult": ...    # WF/DSR/PBO/cost/benchmarks

class PromotionGate(Protocol):
    def check(self, candidate: "PromotionCandidate") -> "GateResult": ...              # PASS/FAIL + evidence

class Narrator(Protocol):                                # local LLM (optional)
    def act(self, state: "OrchestratorState") -> list["ToolCall"]: ...                 # structured calls ONLY
    def narrate(self, event: dict) -> str: ...

class Orchestrator(Protocol):
    def step(self, now: datetime) -> "OrchestratorState": ...   # one observe→…→narrate iteration

class StateReader(Protocol):                             # read-only, for ui/viz3d
    def snapshot(self, run_id: RunId) -> "UIState": ...
    def graph(self, run_id: RunId) -> "GraphPayload": ...
    def tape(self, run_id: RunId, after_seq: int) -> list[dict]: ...
```
`make_order(intent: OrderIntent, decision: RiskDecision) -> Order` is the **only** function that constructs `Order`; it asserts `decision.verdict != "REJECT"`. Enforced by an AST test.

## 11.3 Event schema (field-by-field)
Envelope (every event):
```jsonc
{ "event_id":"uuid","run_id":"uuid","seq":123,"book":"tracked|sandbox",
  "sim_ts":"…Z","wall_ts":"…Z","type":"FillEvent","prev_hash":"sha256","hash":"sha256","payload":{…} }
```
Payloads (types): `MarketEvent{exchange,symbol,timeframe,ts_open,o,h,l,c,v,bid?,ask?,source_version}` · `SignalEvent{strategy,symbol,direction:LONG|SHORT|FLAT,strength:0..1,intent_kind:ENTER|EXIT|REBALANCE,bar_ts,reason}` · `OrderIntent{intent_id,signal_ref,strategy,symbol,side:BUY|SELL,qty,order_type:MARKET|LIMIT,limit_px?,idempotency_key,reason}` · `RiskDecision{intent_ref,verdict:APPROVE|CLAMP|REJECT,approved_qty,rule_hits[],detail}` · `Order{order_id,intent_ref,side,qty,order_type,limit_px?,status:PENDING|ACCEPTED|PARTIALLY_FILLED|FILLED|CANCELLED|REJECTED|EXPIRED}` · `FillEvent{order_id,fill_ts,fill_px,fill_qty,fee,slippage_bps,partial}` · `PositionEvent{symbol,qty,avg_px,realized_pnl,unrealized_pnl,fees_paid}` · `RiskStateEvent{equity,cash,daily_pnl,gross_exposure,peak_equity,drawdown,open_orders,breaches[],kill_active}` · `ControlEvent{command:START|STOP|KILL|FREEZE|FLATTEN|AUTOPILOT_ON|AUTOPILOT_OFF,source,operator,note}`.
Autonomy payloads: `HypothesisEvent{hypo_id,rationale,target_models[],proposed_space,regime}` · `TrialEvent{trial_id,hypo_id,study_id,params,oos_metric,seed,index}` · `ValidationEvent{candidate_id,result:PASS|FAIL,dsr,pbo,cost_survived,beats_equal_weight,evidence}` · `PromotionEvent{candidate_id,from:sandbox,to:tracked,config_version}` · `DeRiskEvent{reason,models[],action:REDUCE|PAUSE|RETIRE}` · `NarrationEvent{text,refs[]}`.

## 11.4 Data & storage schemas
- **OHLCV Parquet** (curated): `ts_open:ts[UTC], exchange, symbol, timeframe, open,high,low,close,volume:float64, trades:int64?, source_version, is_gap_filled:bool` — partitioned `exchange=/symbol=/timeframe=/year=/month=`.
- **Symbol registry:** `canonical PK, exchange, native_symbol, base, quote, active:bool, listed_at, delisted_at` (survivorship-safe).
- **Replay bundle:** dir + `bundle.json{bundle_id,symbols[],tf,start,end,source_versions[],checksum,seed}`.
- **DuckDB catalog tables:** `data_versions(version_id PK,exchange,symbol,timeframe,path,rows,checksum,fetched_at,validated,report:json)` · `experiments(run_id PK,mode,book,strategy,params:json,data_version,git_sha,seed,date_start,date_end,split,sharpe,dsr,pbo,max_dd,turnover,n_trades,cost_bps,passed_gate:bool,created_at,notes)` · `trials(trial_id PK,run_id,study_id,hypo_id,params:json,oos_metric,seed,idx,created_at)` · `promotions(candidate_id PK,run_id,config_version,from,to,validation:json,promoted_at)` · `audit(event_id PK,run_id,seq,book,type,sim_ts,wall_ts,payload:json,prev_hash,hash)` · `daily_reports(run_id,session_date,start_equity,end_equity,pnl,n_trades,wins,losses,max_intraday_dd,fees,breaches:json,reconciled:bool,report_path, PK(run_id,session_date))`.
- **Audit JSONL** is source of truth; DuckDB `audit` is a queryable mirror.

## 11.5 Config schemas (pydantic; lockout enforced)
```yaml
engine: {mode: backtest|paper, clock: replay|wallclock, seed: int, base_currency: str, starting_cash: number}
data:   {adapter: ccxt|csv_replay, exchange: str, symbols: [Symbol], timeframe: Timeframe, replay_bundle: str|null}
strategies: [{name, module, params, book: tracked|sandbox, budget: 0..1}]
risk:   {max_daily_loss, max_dd, max_pos_symbol, max_gross_exposure, max_orders_per_day, max_orders_per_min,
         symbol_whitelist:[Symbol], max_staleness_bars, cash_only: bool, per_strategy_budget, autopilot_may_tune: bool}
autopilot: {enabled: bool, tempo: conservative|aggressive, max_concurrent_trials: int,
            min_trades_for_promotion: int, promote_requires_gate: true, llm: {enabled: bool, model: str, temperature: number}}
execution: {adapter: paper, slippage:{model: fixed_bps|spread|participation, bps}, commission:{model: bps, taker_bps, min_fee}}
reporting: {audit_path, report_path}
```
`engine.mode` Enum excludes `live`; `execution.adapter` Enum = `{paper}` only; `autopilot.promote_requires_gate` is a constant `True`. Load-time validation raises `ConfigError`/`LockoutViolation` on violation.

## 11.6 Autonomy contracts (implementation detail)
```python
class SearchSpace(BaseModel):            # per-model tunable ranges (from manifest params_schema)
    model_id: str; ranges: dict[str, tuple]   # {"fast":(5,50),"slow":(20,200)}

class PromotionCandidate(BaseModel):
    candidate_id: str; model_id: str; params: dict; book: Literal["sandbox"]
    hypo_id: str; study_id: str; data_version: str; seed: int; n_trials_context: int  # honest trial count

class GateResult(BaseModel):
    verdict: Literal["PASS","FAIL"]; dsr: float; pbo: float; cost_survived: bool
    beats_equal_weight: bool; beats_random: bool; walk_forward_oos: float; evidence: dict
    # only Validator/PromotionGate may construct this; Narrator/LLM cannot set verdict.
```
**LLM tool-call schema** (the only outputs the Narrator may emit into the loop):
```jsonc
{"tool":"propose_space","args":{"model_id":"donchian_breakout","ranges":{"lookback":[10,80]},"rationale":"vol expanding"}}
{"tool":"run_trials","args":{"space_ref":"…","n_trials":60,"seed":123}}
{"tool":"promote_if_valid","args":{"candidate_id":"…"}}          // runs the gate; promotes ONLY on PASS
{"tool":"de_risk","args":{"model_id":"…","action":"PAUSE"}}
{"tool":"narrate","args":{"text":"…","refs":["trial_id","candidate_id"]}}
```
The orchestrator executes only these tools; any other output is logged and ignored. `promote_if_valid` calls `PromotionGate.check`; a FAIL logs a `ValidationEvent` and the candidate is discarded. **No tool can place/size an order, disable the kill switch, or set `validated`.**

**Orchestrator loop (state machine):** `OBSERVE → HYPOTHESIZE → SEARCH → VALIDATE → DECIDE → NARRATE → (idle until next tick)`. Deterministic given inputs + seed + recorded LLM actions. Rule-based orchestrator implements the same states without an LLM.

**Sandbox vs tracked books:** both built by `make_session`; sandbox runs experiments (unvalidated, may be aggressive), tracked runs only promoted configs. A promotion copies a validated config from sandbox context into the tracked book atomically, emitting `PromotionEvent`.

## 11.7 Key sequence flows
**Backtest:** load config → build replay bundle → `make_session(ReplayClock, CsvReplay/Parquet)` → loop: MarketEvent → Strategy.on_market → SignalEvent → sizing → OrderIntent → `RiskModel.check` → `make_order` → PaperBroker → FillSimulator → FillEvent → accounting → audit → Analytics.metrics/tearsheet → registry row.
**Live paper tick:** `WallclockClock` + `CcxtMarketDataAdapter` (live public) → same loop; stale-data guard: if last bar older than `max_staleness_bars` → no trade + `DATA_STALE` flag.
**Autonomy iteration:** Orchestrator.step → OBSERVE (perf+drift+regime from audit/StateReader) → HYPOTHESIZE (LLM or rules → `propose_space`) → SEARCH (`Optimizer.study`, each trial = WF backtest on held-out data) → VALIDATE (`PromotionGate.check` on best) → DECIDE (PASS→`PromotionEvent`; FAIL→`ValidationEvent`, learn) → NARRATE.
**Degradation:** drift/threshold breach on tracked book → `DeRiskEvent(REDUCE|PAUSE)` immediately → trigger a fresh SEARCH+VALIDATE cycle → replacement promoted only on gate PASS; repeated failure → `RETIRE`.
**Kill/freeze:** `ControlEvent(KILL)` → persist flag → stop new orders, cancel working, optional FLATTEN → autonomy halts → only human `Clear kill` resumes.

## 11.8 Determinism & audit contract
- `hash = sha256(prev_hash + canonical_json(record_without[hash]))`; canonical_json = sorted keys, fixed float format.
- Audit **excludes** volatile fields (`event_id, wall_ts`) from the hashed portion so identical inputs+seed reproduce the chain; `run_id` fixed per run.
- Every LLM call logs `{prompt, response, model, seed, temperature}`; a session replays by re-applying logged tool-calls (not re-invoking the LLM). Replay-equality + backtest↔paper parity asserted in CI.

## 11.9 StateReader → UI/3D payloads
```jsonc
UIState { mode, autopilot:{on,tempo}, kill_active, session:{equity,pnl,exposure,drawdown},
          books:{tracked:{models[…]},sandbox:{count}}, risk:{breaches[]}, data_health:{per_symbol:{last_bar,gaps}} }
GraphPayload {                                  // for viz3d (three.js/3d-force-graph)
  nodes:[{id,label,family,kind:"tracked|sandbox|meta|regime",state:"ARMED|LONG|SHORT|FIRED|HALTED",
          conviction:0..1,sim_return,n_trades,status:"unproven|validated"}],
  links:[{source,target,kind:"corr+|corr-|dataflow|attention|promotion",weight:0..1}],
  regions:{tracked:[ids],sandbox:[ids]} }
```
UI polls `snapshot`/`tape(after_seq)`; the 3D view builds from `graph`. Both are **read-only**; the only writes are whitelisted `ControlEvent`s via `live.control` (START/STOP/KILL/FREEZE/FLATTEN/AUTOPILOT_ON|OFF). Honesty fields (`n_trades,status`, and a global `simulated:true`) are always present.

## 11.10 Error & failure-mode contract (expected behavior)
| Condition | Behavior |
|---|---|
| Bad/failed data validation | `DataQualityError`; quarantine partition; do not enter curated; ingest continues other ranges |
| Stale/late live data | No trade on that symbol; `DATA_STALE` flag; audited |
| Risk REJECT | No order; `RejectEvent` with rule_hits; audited |
| Gate FAIL | Candidate discarded; `ValidationEvent(FAIL)`; not promoted |
| Reconciliation mismatch | `ReconciliationError`; halt book; audit; require rebuild-from-audit |
| LLM unavailable/timeout | Fall back to rule-based orchestrator; templated narration; no functional loss |
| Attempt to construct Order off-path | `LockoutViolation` (AST test prevents at build) |
| Any live/broker import | CI safety test fails the build |
| Network error (ccxt) | Retry w/ backoff at adapter; on exhaustion → no trade + flag; never blocks the decision loop nondeterministically |

## 11.11 Non-functional requirements
- **Determinism:** identical inputs+seed → identical audit hashes (hard).
- **Performance (targets):** backtest ≥ 50k bars/s single-thread on a laptop; live loop comfortably < bar interval; 3D view ≥ 30 fps at ≤ ~150 nodes (instanced), throttle updates to 1–2 Hz.
- **Locality/security:** bind `127.0.0.1` only; no auth because unreachable; no credentials anywhere; no outbound except ccxt public + optional local Ollama.
- **Resource bounds:** sandbox trial concurrency capped by `max_concurrent_trials`; bounded job queue; audit log rotation by run.
- **Accessibility:** UI WCAG AA, keyboard-first, `prefers-reduced-motion`; 3D degrades to 2D.
- **Licensing:** runtime deps MIT/BSD/Apache/NCSA (CI `pip-licenses` gate); local-LLM weights verified before any distribution.

## 11.12 Test contract (what each suite must assert)
- **safety:** only `PaperBroker` implements `ExecutionAdapter`; `is_paper` asserted at startup; no broker SDK / ccxt order call anywhere; config rejects live; one `Order` constructor after risk; kill un-overridable by LLM; PromotionGate un-bypassable; UI/3D/narrator construct no `Order`.
- **honesty:** GUI renders no raw stdout; sandbox≠tracked never conflated; sample sizes + `simulated`/`unproven` present; no profit-language (lint); `validated` only after a gate PASS.
- **determinism/parity:** two runs → identical hashes; replay reproduces session incl. autonomy; backtest↔paper parity.
- **property (hypothesis):** no intent sequence breaches limits; accounting conservation (cash+positions==equity).
- **data:** every §8.4 check fires on injected bad data; gaps ⇒ no trade.
- **integration:** full v0.x flows end-to-end.

## 11.13 System acceptance & traceability
System is acceptable when: paper-only lockout proven · promotion gate un-bypassable and enforced before autonomy · determinism/replay + parity hold · GUI has no CLI and honesty overlays present · autopilot aggressive but audited + reversible · 3D interactive + replayable + read-only · license gate green · no profitability claims. Each maps to a milestone exit gate in [`10`](10-production-roadmap.md) (safety→M1/M5/M9, gate→M4, catalog→M6/M11, UI→M7, autonomy→M8, autopilot/LLM→M9, 3D→M10, hardening/release→M12).

> This spec is the contract; the `tests/safety` and `tests/honesty` suites are its executable enforcement. If a change can't keep both green, the change is wrong.
