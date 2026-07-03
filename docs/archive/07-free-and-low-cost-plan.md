# 07 — Free and Low-Cost Plan

**Goal:** a concrete, staged path that keeps non-Claude spend at **$0/month** through the entire MVP, with explicit "pay only when X happens" triggers. This is the operational companion to [`06-cost-analysis.md`](06-cost-analysis.md).

## 7.1 The fully-free stack (what you run and why it's $0)

| Need | Free tool | License | Why it's genuinely free |
|---|---|---|---|
| Language/runtime | Python 3.12+ | PSF | Free |
| Crypto data (history + live) | `ccxt` → exchange public endpoints | MIT | Public market data needs no key/account ([ccxt](https://docs.ccxt.com/)) |
| Storage / query | Parquet + DuckDB + Polars | MIT | Embedded, no server, no cloud ([DuckDB](https://duckdb.org)) |
| Indicators | pandas-ta | MIT | Pure Python, no build |
| Analytics | QuantStats | Apache-2.0 | Local tearsheets |
| Portfolio math (later) | skfolio / PyPortfolioOpt | BSD-3 / MIT | Local |
| Models (later) | statsmodels / arch / hmmlearn / ruptures | permissive | Local |
| UI | NiceGUI (localhost) | MIT | No hosting ([NiceGUI](https://nicegui.io)) |
| Paper broker | your own sim | yours | Deterministic, no vendor |
| Notebooks | JupyterLab | BSD | Local |
| Version control | Git + GitHub free private | — | Free tier ([GitHub pricing](https://github.com/pricing)) |
| Packaging (later) | pywebview → PyTauri | BSD / MIT+Apache | Free to build unsigned `.exe` |
| Build labor | Claude Code Pro | — | $20/mo (or $0 marginal on existing plan) |

## 7.2 Free-data experiments you can run today (crypto-first)

1. **Historical OHLCV pull** — `ccxt` `fetch_ohlcv` across BTC/USDT, ETH/USDT, a few majors, multiple timeframes (1m/5m/1h/1d); paginate to build years of history; store as partitioned Parquet.
2. **Live quote stream** — `ccxt.pro`-style / public WebSocket for real-time ticks/bars into the paper loop.
3. **Data-quality lab** — detect gaps, duplicate timestamps, out-of-order bars, zero/negative prices, impossible OHLC (`high < low`), and exchange outages. (This *is* Milestone 2.)
4. **Cross-exchange sanity** — compare the same pair across Binance/Kraken/Coinbase to catch bad prints.
5. **Cost-sensitivity study** — re-run a backtest at 0/5/10/20 bps slippage; watch edges evaporate. Free, and the most valuable experiment you'll do.

**Free-data caveats to bake in:** rate limits (Kraken ~1 req/s, Coinbase 300 rows/req, Binance weight budget) ([Kraken limits](https://support.kraken.com/articles/206548367)); no uptime SLA; possible ToS limits on redistribution (keep data local, don't republish); crypto is 24/7 (no market-hours calendar, but exchange maintenance gaps happen).

## 7.3 "Pay only when…" trigger list (decision points, not monthly creep)

| Trigger | Then consider paying for | Rough cost | Why wait |
|---|---|---|---|
| A strategy graduates from backtest → serious paper trading and you need clean history | vetted crypto history (Kaiko/CoinAPI) or careful multi-exchange validation | $0–$100s/mo | Free data may hide gaps that flatter results |
| You move to **equities/futures** | reliable feed (Polygon/Tiingo/Databento/Alpaca+) | $10–$200/mo | Free equity real-time is IEX-only/partial ([Alpaca](https://alpaca.markets/data)) |
| Claude Code Pro limits block multi-hour build sprints | Max 5x/20x | $100/$200/mo | Only during heavy sprints; revert after |
| You want to **distribute** the Windows app to others | code-signing certificate | ~$100–$400/yr | Avoids SmartScreen warnings; unnecessary for personal use |
| You seriously consider **live trading** (out of MVP scope) | broker account + **professional review** (legal/tax/compliance) | varies | Never skip pro review before real money — see [`14`](14-safety-risk-and-compliance-review.md) |
| Research sweeps get painfully slow | vectorbt PRO (research only) | $20/mo | Free vectorbt/your engine likely suffices at MVP scale |

## 7.4 Staged rollout (each stage stays $0 non-Claude)

- **Stage 0 — Setup ($0):** repo, Python env, config, Git. No data yet.
- **Stage 1 — Local research ($0):** ccxt history → Parquet → Jupyter exploration + data-quality checks.
- **Stage 2 — Backtest + UI ($0):** deterministic engine + replay + QuantStats reports surfaced in NiceGUI.
- **Stage 3 — Paper trading ($0):** PaperBroker + risk engine + kill switch, fed by ccxt live public feed.
- **Stage 4 — Hardening ($0):** audit review, parity tests, safety gates, lockout proof.
- **Stage 5 — Optional packaging ($0 unsigned):** wrap UI in a desktop window (pywebview/PyTauri).

You never *have* to leave $0 to complete a serious research + paper-trading system. Money enters only at the deliberate triggers above.

## 7.5 What $0 buys you — and what it doesn't

**Buys:** a complete, auditable, deterministic research + paper-trading engine on crypto data, with real risk controls, a local UI, and a clean upgrade path.

**Doesn't buy:** guaranteed-clean data, real-time equities/futures, an uptime SLA, legal/tax cover for live trading, or a signed distributable. Those are *later, deliberate* purchases — and none of them are needed to prove out the system or your research discipline.

> **The honest punchline:** the binding constraint on this project is **not money** — it's **research discipline** (avoiding overfitting/look-ahead) and **safety engineering** (never trading live by accident). Both are free to get right and expensive to get wrong. Spend your effort there, not on tooling. See [`09`](09-backtesting-research-protocol.md) and [`14`](14-safety-risk-and-compliance-review.md).
