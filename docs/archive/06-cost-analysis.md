# 06 — Cost Analysis

**Budget setting (from you):** **$0/month strict** for the MVP, excluding your Claude Code/Cowork usage (costed separately below). This file proves a $0 data/compute/UI path exists and marks the exact points where paying later becomes worth it.

> All prices verified July 2026 and **will drift** — re-check vendor pages before committing. `[Guessing]` marks figures I could not pin to a single authoritative page.

## 6.1 The master cost table

| Item | Free option | Paid option | Est. cost range | Trade-offs | Recommendation | Source | MVP? |
|---|---|---|---|---|---|---|:--:|
| **Claude Code (build labor)** | — (trial only) | Pro / Max 5x / Max 20x | **$20 / $100 / $200 per mo** | Pro is enough for paced solo work; Max for heavy multi-hour sessions | **Start Pro $20**; upgrade only if you hit limits | [claude.com/pricing](https://claude.com/pricing) | ✅ (the one real cost) |
| Claude API (if not subscription) | — | Sonnet $2/$10→$3/$15 per MTok | usage-based | Subscription is far cheaper for heavy use | Use subscription, not API | [pricing](https://claude.com/pricing) | ➖ |
| **Local compute** | Your PC | Cloud VM | **$0** | Your Windows box runs everything | **Local only** | — | ✅ |
| **Cloud compute** | n/a | AWS/GCP/Hetzner | $5–$50+/mo | Not needed for local research/paper | **Skip in MVP** | — | ❌ |
| **Historical data (crypto)** | Exchange public REST (Binance/Kraken/Coinbase) via ccxt; Kraken CSV dumps | Kaiko/CoinAPI/Databento | $0 vs $100s–$1000s/mo | Free = paginated, rate-limited, self-validated | **Free (crypto)** | [ccxt](https://github.com/ccxt/ccxt), [Kraken CSV](https://support.kraken.com/articles/360047124832) | ✅ |
| **Historical data (equities)** | Stooq, yfinance (unofficial), Alpaca | Polygon/Tiingo/EODHD | $0 vs $10–$200/mo | Free equities = daily/delayed, ToS gray areas | **Defer** (crypto-first) | [Alpaca data](https://alpaca.markets/data) | ❌ |
| **Real-time data (crypto)** | Exchange public WebSocket via ccxt | Paid low-latency feeds | **$0** vs $100s | Free public WS is fine for research/paper | **Free (crypto)** | [ccxt](https://docs.ccxt.com/) | ✅ |
| **Real-time data (equities)** | Alpaca Basic (IEX only) | Alpaca Algo Trader+, Polygon | $0 (partial) vs $99+/mo | Free = IEX-only, not full-market | **Defer** | [Alpaca data](https://alpaca.markets/data) | ❌ |
| **Paper trading** | Your `PaperBroker` (simulated) + Alpaca paper | — | **$0** | Your own sim = full control/determinism | **Own PaperBroker** | [Alpaca paper](https://docs.alpaca.markets/us/docs/paper-trading) | ✅ |
| **Broker / API access** | Alpaca paper account (email only) | Live brokerage | **$0** (paper) | No credentials in MVP (constraint #2) | **None in MVP** | [Alpaca paper](https://docs.alpaca.markets/us/docs/paper-trading) | ❌ |
| **Storage** | Local Parquet + DuckDB | Cloud object storage | **$0** | GBs fit locally; Parquet compresses well | **Local Parquet/DuckDB** | [DuckDB](https://duckdb.org) | ✅ |
| **UI hosting** | localhost (NiceGUI) | Cloud host | **$0** | Local desktop app, nothing exposed | **localhost only** | [NiceGUI](https://nicegui.io) | ✅ |
| **Monitoring / logging** | Local files (JSONL) + `structlog` | Datadog/Sentry | **$0** | Local audit log is sufficient at this scale | **Local files** | — | ✅ |
| **Research notebooks** | JupyterLab (BSD) local | Colab Pro/Deepnote | **$0** vs $10+/mo | Local Jupyter is plenty | **Local Jupyter** | [jupyter.org](https://jupyter.org) | ✅ |
| **Version control** | Git + GitHub free/private | GitHub Team/GitLab paid | **$0** | Free private repos suffice | **Git + free GitHub** | [github.com/pricing](https://github.com/pricing) | ✅ |
| **Deployment / packaging** | run `python -m`; later pywebview/PyTauri | Code-signing cert | **$0** now; ~$100–$400/yr cert if you distribute signed `.exe` | Unsigned `.exe` triggers SmartScreen warnings | **Free now**; sign only if distributing | [PyTauri](https://github.com/pytauri/pytauri) | ✅ (build) / ❌ (sign) |
| **Optional paid tools** | — | vectorbt PRO ($20/mo), TradingView, Databento | $10–$200/mo | Nice-to-haves, not needed | **Skip** | [vectorbt PRO](https://vectorbt.pro/) | ❌ |
| **Legal / accounting / compliance** | Self-education (non-advice) | Lawyer/CPA consult | $0 now; $200–$500+/hr later | Only relevant *before live trading* | **Defer to pre-live** | see [`14`](14-safety-risk-and-compliance-review.md) | ❌ |

**MVP total, excluding Claude Code: `$0/month`.** Including Claude Code: **$20/month** (Pro) — and **$0 marginal** if you already run a Claude Max plan for other work.

## 6.2 Your twelve cost questions, answered

1. **Can this be built nearly free?** **[Certain] Yes.** Every runtime component has a $0 path; the only unavoidable spend is Claude Code (from $20/mo, or $0 marginal on an existing plan).
2. **What can be fully free & open-source?** The entire engine, storage (Parquet/DuckDB/Polars), indicators (pandas-ta), analytics (QuantStats), crypto data (ccxt public endpoints), UI (NiceGUI), notebooks (Jupyter), and version control (Git/GitHub free). All MIT/BSD/Apache-2.0.
3. **What is likely *not* free if you want reliable data?** **[Certain]** Reliable **real-time equities/futures** and clean, survivorship-bias-free, corporate-action-adjusted **historical equities** data. That's a paid decision point ($10–$200+/mo), deferred because you're crypto-first.
4. **What data sources have free tiers?** Crypto exchange public APIs (Binance/Kraken/Coinbase via ccxt, no key) ([Kraken API](https://www.kraken.com/features/trading-api)); **Alpaca** (free paper + free IEX real-time + simulated crypto) ([Alpaca](https://alpaca.markets/data)); Stooq/yfinance (unofficial); Kaggle/public datasets; Kraken downloadable OHLCVT CSV.
5. **Limitations of free data?** Rate limits (Kraken ~1 req/s public; Binance weight budget; Coinbase 300 rows/req) ([Kraken limits](https://support.kraken.com/articles/206548367)); pagination for history; **no reliability/uptime SLA**; possible ToS restrictions (esp. yfinance/redistribution); gaps, bad prints, and no corporate-action handling. Treat free data as *self-validated and possibly wrong*.
6. **What can be done with delayed/CSV/public/downloaded historical data?** Essentially **all research and backtesting**, plus paper trading on a lag. Backtests don't need real-time; they need *clean, point-in-time* history — which downloaded CSV/Parquet provides once validated.
7. **Crypto exchange public APIs for research/paper only?** **[Certain]** Fully sufficient: public REST for history, public WebSocket for live quotes, no API key, no credentials — perfectly matched to constraint #2. ([ccxt](https://docs.ccxt.com/))
8. **What can be done locally with no cloud spend?** Everything in the MVP: ingest, validate, store, backtest, replay, analyze, paper-trade, and view the UI — all on your PC.
9. **What should you NOT cheap out on later?** (a) **Data quality** before serious paper/live; (b) **backtest realism** (costs/slippage) — free to do, expensive to skip; (c) **a real code-signing cert** if you distribute a Windows app; (d) **professional review** (broker/data ToS, tax, legal) *before any live trading*. Cheaping out here is how you get silently wrong results or a nasty surprise.
10. **Lowest-cost serious MVP plan?** Custom core + ccxt crypto data + Parquet/DuckDB + NiceGUI + Claude Code Pro. **$20/mo total.** See [`07`](07-free-and-low-cost-plan.md).
11. **Lowest-cost serious paper-trading plan?** Your `PaperBroker` (deterministic sim) fed by ccxt public WebSocket, with the risk engine + kill switch. **$0/mo** on top of the MVP.
12. **Realistic monthly cost ranges:**

| Stage | Non-Claude cost | With Claude Pro | Notes |
|---|---|---|---|
| Local research only | **$0** | $20 | ccxt + Parquet + Jupyter |
| Backtesting + UI | **$0** | $20 | + NiceGUI |
| Paper trading, free/delayed data | **$0** | $20 | crypto public WS; self-validated |
| Paper trading, *reliable real-time* data | **$0 (crypto)** / **$50–$200 (equities/futures)** | +$20 | crypto stays free; equities/futures = paid feed |
| Future live-readiness (excl. capital) | **~$50–$300+/mo** `[Guessing]` | +$20 | reliable data + possibly code-signing + pro review (one-off) |

## 6.3 Cost risks & caveats

- **Claude Code overage.** Heavy multi-hour agentic sessions can exhaust Pro limits; Max 5x/20x exist for that. Budget for the possibility you upgrade to $100/mo during intense build sprints, then drop back. ([pricing](https://claude.com/pricing))
- **"Free forever" is not guaranteed.** Exchange public-API terms and Alpaca free tiers change. Keep the data layer behind the adapter so a terms change is a swap, not a rewrite.
- **Hidden time cost.** The real cost of the $0 path is *your time* validating free data. That's why data-quality checks are a first-class MVP feature ([`08`](08-data-strategy.md)), not an afterthought.
- **Don't confuse "free to build" with "safe to trade."** $0 covers research and paper. Live trading introduces capital risk and professional-review costs that are out of scope here by design.
