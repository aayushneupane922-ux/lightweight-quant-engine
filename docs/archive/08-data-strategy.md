# 08 — Data Strategy

**Scope:** crypto-first, asset-agnostic. Everything here sits behind `MarketDataAdapter` so equities/futures/Sierra plug in later without touching the engine. **No data is trusted until validated.**

## 8.1 Data types — what the MVP needs vs. defers

| Data | MVP? | Notes |
|---|:--:|---|
| **OHLCV bars** | ✅ **Primary** | 1m/5m/1h/1d from ccxt; the backbone of all MVP strategies |
| Trades/tick data | ➖ optional | ccxt can fetch trades; heavy; only if a strategy needs it |
| Order-book (L2) data | ❌ later | Microstructure is out of MVP scope |
| Corporate actions | ❌ n/a crypto | Relevant for equities later (dividends/splits) |
| Dividends/splits | ❌ n/a crypto | Equities-only; adjust prices point-in-time when added |
| Futures rolls | ❌ later | Only if/when futures added; continuous-contract construction is its own project |
| Crypto data | ✅ | Spot pairs; 24/7; no market calendar but exchange-maintenance gaps exist |
| Funding rates / perps | ❌ later | Perp funding is a later crypto extension |

## 8.2 The hard, cross-cutting concerns (get these right or results lie)

- **Time zones:** store **everything in UTC**, tz-aware. Bar timestamps are **left-edge (open) time**, documented and consistent. Convert to local only at the UI edge.
- **Bar-timing / look-ahead:** a bar timestamped `t` represents `[t, t+Δ)`. A strategy may only act on bar `t` at or after `t+Δ` (it isn't "complete" until then). This one rule prevents the most common backtest fraud. Enforced in the engine, tested explicitly.
- **Missing data:** detect gaps (expected vs. actual bar count), don't silently forward-fill in storage; forward-fill only inside a strategy if it explicitly opts in, and log it. Gaps → *no trade over the gap*, flagged.
- **Symbol mapping:** exchanges disagree (`BTC/USDT` vs `XBT/USD` vs `BTC-USD`). Maintain a **canonical symbol registry** mapping `(exchange, native_symbol) → canonical_symbol`; strategies see only canonical symbols.
- **Survivorship bias:** delisted/depegged pairs must remain in history. Never build a universe from *currently-listed* symbols and backtest the past on it. For crypto, track delistings/renames in the symbol registry.
- **Lookahead bias:** beyond bar-timing — never use restated/adjusted values that weren't known at `t`; compute indicators causally; split data *before* any fitting.
- **Data versioning:** each ingest writes an immutable, dated Parquet partition + a manifest row (source, exchange, symbol, timeframe, rows, checksum, fetch time). Re-fetches create a new version; you can always reproduce which bytes a backtest used.

## 8.3 Recommended MVP data format & storage

**Format:** partitioned **Parquet** for bars (columnar, compressed, portable), queried via **DuckDB**; run/experiment metadata in a small **DuckDB or SQLite** catalog. Polars/PyArrow for transforms. Rationale + benchmarks: [`02`](02-open-source-framework-matrix.md), [DuckDB+Parquet for finance](https://questdb.com/blog/why-parquet-matters-for-time-series-and-finance/).

**Folder structure:**

```
data/
  raw/                         # immutable pulls, never edited
    ohlcv/
      exchange=binance/
        symbol=BTC-USDT/
          timeframe=1m/
            year=2024/month=01/part-0000.parquet
            _manifest.jsonl    # one row per fetch: source, rows, checksum, fetched_at
  curated/                     # validated, gap-annotated, canonical symbols
    ohlcv/exchange=.../symbol=.../timeframe=.../year=.../month=.../*.parquet
  reference/
    symbols.parquet            # canonical symbol registry + mappings + delistings
    calendars.parquet          # (crypto: 24/7; placeholder for equities/futures)
  replay/                      # deterministic replay bundles for tests/backtests
    <bundle_id>/events.parquet + bundle.json (checksums, date range, symbols)
catalog.duckdb                 # experiments, runs, data versions, validation results
```

**Bar schema (curated OHLCV):**

| column | type | notes |
|---|---|---|
| `ts_open` | timestamp[UTC] | bar left-edge (primary sort key) |
| `exchange` | string | e.g. `binance` |
| `symbol` | string | canonical, e.g. `BTC-USDT` |
| `timeframe` | string | `1m`,`5m`,`1h`,`1d` |
| `open/high/low/close` | float64 | |
| `volume` | float64 | base-asset volume |
| `trades` | int64 | if available (Kraken provides) |
| `source_version` | string | manifest id for reproducibility |
| `is_gap_filled` | bool | true if synthesized to fill a gap (default false) |

## 8.4 Data-quality checks (must pass before curated/ and before any backtest)

Run as a validation stage (Pandera schema + custom rules). **Fail loudly; quarantine, don't silently fix.**

1. **Monotonic, unique timestamps** per (exchange, symbol, timeframe).
2. **No duplicate bars**; no out-of-order bars.
3. **OHLC sanity:** `low ≤ open,close ≤ high`; `high ≥ low`; no non-positive prices.
4. **Volume ≥ 0**; flag suspicious zero-volume bars.
5. **Gap report:** expected vs. actual bar count for the range; list missing intervals; annotate, don't forward-fill in storage.
6. **Outlier prints:** returns beyond N·rolling-σ flagged for review (possible bad ticks) — flag, don't auto-delete.
7. **Cross-source spot check** (optional): same pair on a second exchange within tolerance.
8. **Checksum + manifest** written; validation result recorded in `catalog.duckdb`.

## 8.5 Replay format (deterministic)

A **replay bundle** is a frozen, checksummed set of events for a date range + symbol set, plus a `bundle.json` (symbols, range, source versions, checksum, RNG seed). Backtests and parity tests consume bundles, guaranteeing the *exact same bytes* every run. This is the substrate for constraint #6 (deterministic replay) and the backtest↔paper parity tests.

## 8.6 What data is acceptable when

| Purpose | Acceptable data |
|---|---|
| Early research / prototyping | Free ccxt history, even with minor gaps (documented); public datasets; CSV |
| Backtesting a candidate strategy | **Validated curated Parquet** (passes §8.4), point-in-time, survivorship-aware |
| Serious paper trading | Validated curated history **+** live public WebSocket, with stale-data checks |
| (Future) live trading — out of scope | Reliable, SLA-backed, licensed feed + professional ToS review |

## 8.7 Ingestion pipeline (logical stages)

```
fetch (ccxt, rate-limited, paginated)
  → land raw/ Parquet + manifest (immutable)
  → validate (§8.4)  ── fail → quarantine + report
  → normalize (canonical symbols, UTC, dtype) → curated/
  → register version in catalog.duckdb
  → (on demand) build replay bundle for a run
```

Rate-limit handling lives in the adapter (backoff, respect per-exchange limits). Ingestion is **idempotent**: re-running fetches only missing ranges; never mutates raw partitions.

## 8.8 Recommendations (summary)

- **MVP data format:** partitioned Parquet + DuckDB catalog; canonical symbol registry; UTC left-edge bars.
- **Free experiments first:** crypto OHLCV via ccxt; make the data-quality lab (§8.4) a Milestone-2 deliverable, not a "later" nicety.
- **Paid decision points:** only when graduating a strategy to serious paper trading (clean crypto history) or moving to equities/futures (reliable feed). See triggers in [`07`](07-free-and-low-cost-plan.md).
- **Golden rule:** *validate before you trust, version before you backtest, and let gaps mean "no trade," never "guess."*
