# 12 — Event & Storage Schema

Reference schemas Claude Code should implement directly. Types are pydantic models in Python; storage is Parquet + DuckDB. **All timestamps are UTC, tz-aware, ISO-8601 with `Z`.** Money/qty use `Decimal` (or documented fixed-precision float). Every persisted record carries provenance for replay.

## 12.1 Common envelope (every event)

```json
{
  "event_id": "uuid",
  "run_id": "uuid",
  "seq": 128,                     // monotonic per run
  "sim_ts": "2026-07-02T14:30:00Z",
  "wall_ts": "2026-07-02T14:30:00.123Z",
  "type": "FillEvent",
  "prev_hash": "sha256...",       // hash chain over previous record
  "hash": "sha256...",            // hash of this record (tamper-evidence)
  "payload": { ... }              // type-specific, below
}
```

## 12.2 Event payloads

```jsonc
// MarketEvent
{ "exchange":"binance","symbol":"BTC-USDT","timeframe":"1m",
  "ts_open":"...","open":..,"high":..,"low":..,"close":..,"volume":..,
  "bid":null,"ask":null,"source_version":"manifest-id" }

// SignalEvent
{ "strategy":"trend_ma_cross","symbol":"BTC-USDT","direction":"LONG",
  "strength":1.0,"intent_kind":"ENTER","bar_ts":"...","reason":"fast>slow" }

// OrderIntent
{ "intent_id":"uuid","signal_ref":"event_id","strategy":"...","symbol":"...",
  "side":"BUY","qty":0.10,"order_type":"MARKET","limit_px":null,
  "idempotency_key":"strategy|symbol|side|bar_ts","reason":"..." }

// RiskDecision
{ "intent_ref":"intent_id","verdict":"APPROVE","approved_qty":0.10,
  "rule_hits":[],"detail":{"gross_after":0.6,"cash_after":9000.0} }

// Order
{ "order_id":"uuid","intent_ref":"intent_id","side":"BUY","qty":0.10,
  "order_type":"MARKET","limit_px":null,"status":"ACCEPTED" }

// FillEvent
{ "order_id":"uuid","fill_ts":"...","fill_px":61000.0,"fill_qty":0.10,
  "fee":6.1,"slippage_bps":8.0,"partial":false }

// RejectEvent
{ "ref":"intent_or_order_id","reason":"MAX_POSITION","detail":{...} }

// PositionEvent
{ "symbol":"BTC-USDT","qty":0.10,"avg_px":61000.0,
  "realized_pnl":0.0,"unrealized_pnl":12.3,"fees_paid":6.1 }

// RiskStateEvent
{ "equity":10012.3,"cash":3900.0,"daily_pnl":12.3,"gross_exposure":0.61,
  "peak_equity":10050.0,"drawdown":0.0037,"open_orders":1,
  "breaches":[],"kill_active":false }

// ControlEvent
{ "command":"KILL","source":"ui","note":"manual","operator":"local" }
```

## 12.3 Storage schema (DuckDB catalog: `catalog.duckdb`)

```sql
-- immutable data versions (provenance for reproducibility)
CREATE TABLE data_versions (
  version_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, timeframe TEXT,
  path TEXT, rows BIGINT, checksum TEXT, fetched_at TIMESTAMP,
  validated BOOLEAN, validation_report JSON);

-- canonical symbols + mappings + delistings (survivorship-safe)
CREATE TABLE symbols (
  canonical TEXT PRIMARY KEY, exchange TEXT, native_symbol TEXT,
  base TEXT, quote TEXT, active BOOLEAN, listed_at DATE, delisted_at DATE);

-- experiments / runs (the experiment registry, see 09 §9.10)
CREATE TABLE experiments (
  run_id TEXT PRIMARY KEY, hypothesis_id TEXT, mode TEXT,      -- backtest|paper
  strategy TEXT, params JSON, data_version TEXT, code_git_sha TEXT, seed BIGINT,
  date_start TIMESTAMP, date_end TIMESTAMP, split TEXT,
  sharpe DOUBLE, dsr DOUBLE, pbo DOUBLE, max_dd DOUBLE, turnover DOUBLE,
  n_trades BIGINT, cost_bps DOUBLE, passed_kill_check BOOLEAN,
  created_at TIMESTAMP, notes TEXT);

-- audit mirror (also written as JSONL append-only file)
CREATE TABLE audit (
  event_id TEXT PRIMARY KEY, run_id TEXT, seq BIGINT, type TEXT,
  sim_ts TIMESTAMP, wall_ts TIMESTAMP, payload JSON, prev_hash TEXT, hash TEXT);

-- daily paper reports
CREATE TABLE daily_reports (
  run_id TEXT, session_date DATE, start_equity DOUBLE, end_equity DOUBLE,
  pnl DOUBLE, n_trades BIGINT, wins BIGINT, losses BIGINT, max_intraday_dd DOUBLE,
  fees DOUBLE, breaches JSON, reconciled BOOLEAN, report_path TEXT,
  PRIMARY KEY (run_id, session_date));
```

Bars live in partitioned **Parquet** (schema in [`08`](08-data-strategy.md) §8.3), queried via DuckDB `read_parquet`. Audit is JSONL (source of truth) mirrored into `audit` for querying.

## 12.4 Config schemas (pydantic)

```yaml
# engine config
engine:
  mode: backtest            # backtest | paper   (NO 'live' — schema rejects it)
  clock: replay             # replay | wallclock
  seed: 42
  base_currency: USDT
  starting_cash: 10000

data:
  adapter: ccxt             # ccxt | csv_replay
  exchange: binance
  symbols: ["BTC-USDT","ETH-USDT"]
  timeframe: 1m
  replay_bundle: null       # required for deterministic backtests

strategies:
  - name: trend_ma_cross
    module: strategies.trend_ma_cross
    params: {fast: 20, slow: 50}
    budget: 0.5

risk: { ...see 11 §11.9... }

execution:
  adapter: paper            # paper ONLY (schema rejects other values in MVP)
  slippage: {model: fixed_bps, bps: 10}
  commission: {model: bps, taker_bps: 25, min_fee: 0.0}

reporting:
  audit_path: ./runs/{run_id}/audit.jsonl
  report_path: ./runs/{run_id}/report.md
```

**Live lockout in schema:** `engine.mode` and `execution.adapter` are `Enum`s that **do not contain** `live`/real-broker values in the MVP. A config attempting them fails validation at load. See [`10`](10-paper-trading-engine-spec.md) §10.15, [`14`](14-safety-risk-and-compliance-review.md).

## 12.5 Strategy plugin interface

```python
class Strategy(Protocol):
    name: str
    params: dict
    def on_start(self, ctx: Context) -> None: ...
    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]: ...
    def on_fill(self, ev: FillEvent, ctx: Context) -> None: ...
    # Rules for authors:
    #  - deterministic: no wall-clock, no unseeded RNG, no network
    #  - causal: may only use data with ts <= ev.ts (bar completeness enforced)
    #  - stateless-ish: all state in ctx (so replay reconstructs it)
```

`Context` exposes: read-only market/history access (causal), current positions/equity, indicator helpers (`ctx.indicators` → pandas-ta behind interface), config params, and a logger. Strategies **cannot** submit orders directly — they only emit `SignalEvent`s; sizing + risk decide the rest.

Discovery: strategies are registered via entry-points or a `strategies/` package scan; each ships a manifest (name, params schema, description) surfaced in the UI.

## 12.6 Model plugin interface

```python
class Model(Protocol):
    name: str
    def fit(self, data) -> "Model": ...           # offline/research; never in the live decision path opaquely
    def predict(self, data): ...                   # deterministic given fitted params
    def save(self, path) -> None: ...
    def load(self, path) -> "Model": ...
```

Used for portfolio optimizers (skfolio/PyPortfolioOpt), regime detectors (hmmlearn/ruptures), vol models (arch). A model's output feeds a *deterministic* strategy or sizer; **no model makes an autonomous trade** (constraint #3). Fitted models are versioned artifacts referenced by `run_id`.

## 12.7 Determinism & hashing rules

- Every run: `run_id`, `code_git_sha`, `config_hash`, `data_version`, `seed` recorded.
- Audit records hash-chain (`hash = sha256(prev_hash + canonical_json(record))`).
- Canonical JSON = sorted keys, fixed float formatting — so hashes are reproducible.
- Replay of a run's `MarketEvent`s + config + seed reproduces identical downstream events (asserted in CI).

## 12.8 Symbol & precision conventions

- Canonical symbol: `BASE-QUOTE` upper-case (`BTC-USDT`). Adapter maps native↔canonical.
- Price/qty precision per market recorded in `symbols`; rounding is explicit and logged; no silent precision drift in accounting.
