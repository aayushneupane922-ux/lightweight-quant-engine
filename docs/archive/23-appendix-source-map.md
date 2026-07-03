# 23 — Appendix: Source Map

All primary sources used, grouped by topic, with the specific claim each supports and a confidence note. **Verified July 2026 — licenses, pricing, and maintenance status drift; re-verify before relying on any of this for spending or distribution.** Where a claim is `[Guessing]` it is not backed by a single authoritative page and is flagged as such in-text.

## Frameworks & engines

- **QuantConnect LEAN** — Apache-2.0; open-source; runs locally; **local runs require Docker**.
  - License: https://github.com/QuantConnect/Lean/blob/master/LICENSE · https://www.lean.io/
  - Docker requirement: https://github.com/QuantConnect/lean-cli · https://www.lean.io/docs/v2/lean-cli/key-concepts/getting-started
- **NautilusTrader** — LGPL-3.0; Rust-core + Python API; pip-installable without Docker; active (©2015–2026).
  - License: https://nautilustrader.io/legal/open-source-licensing/ · Repo: https://github.com/nautechsystems/nautilus_trader · Install: https://nautilustrader.io/docs/latest/getting_started/installation/
- **Backtrader** — GPL-3.0; **effectively unmaintained** ("archive mode," no PyPI release in 12+ months).
  - https://community.backtrader.com/topic/3702/is-backtrader-dead · https://community.backtrader.com/topic/2466/backtrader-maintenance
- **vectorbt (open)** — **Apache-2.0 + Commons Clause** (no selling a product "primarily this software"); PRO is commercial (~$20/mo).
  - License: https://vectorbt.dev/terms/license/ · Repo: https://github.com/polakowo/vectorbt · PRO: https://vectorbt.pro/
- **Zipline-reloaded** — Apache-2.0; **actively maintained** (3.1.1, Py3.13/NumPy2.0); daily-equity-centric.
  - https://github.com/stefan-jansen/zipline-reloaded · https://x.com/ml4trading/status/1948303607729631620
- **Qlib** — MIT; active (Microsoft; RD-Agent integration).
  - https://github.com/microsoft/qlib · https://github.com/microsoft/qlib/blob/main/LICENSE
- **FinRL** — MIT; academic/research; active; next-gen "FinRL-X."
  - https://github.com/AI4Finance-Foundation/FinRL
- **TensorTrade** — Apache-2.0; low recent activity. (repo: https://github.com/tensortrade-org/tensortrade)

## Portfolio & analytics libraries

- **skfolio** — BSD-3; sklearn-native portfolio optimization; active.
  - https://skfolio.org/ · https://github.com/skfolio/skfolio · paper: https://arxiv.org/abs/2507.04176
- **PyPortfolioOpt** — MIT (MVO/BL/HRP). https://github.com/robertmartin8/PyPortfolioOpt
- **riskfolio-lib** — BSD-3; cvxpy-based. https://pypi.org/project/riskfolio-lib/
- **QuantStats** — Apache-2.0; `quantstats-reloaded` fork active.
  - https://github.com/ranaroussi/quantstats · https://pypi.org/project/quantstats-reloaded/
- **empyrical** — Apache-2.0; original stale (2020), `empyrical-reloaded` fork active.
- **arch** (GARCH/vol) — permissive; active (bashtage). https://github.com/bashtage/arch
- **statsmodels** (cointegration/ADF) — BSD-3. **hmmlearn** (HMM) — BSD-3. **ruptures** (change-point) — BSD-2 (https://arxiv.org/pdf/1801.00826).
- **pandas-ta** — MIT; maintenance gaps; `pandas-ta-classic` fork active (https://www.pandas-ta.dev/legal/). **TA-Lib** — BSD-3 (C build).

## Data stack & sources

- **ccxt** — MIT; 100+ crypto exchanges; unified REST + WebSocket; free for commercial/OSS.
  - https://github.com/ccxt/ccxt · https://docs.ccxt.com/
- **Crypto public API rate limits** — Binance weight-budget (~6000/min); Coinbase ~10 req/s public + 300 rows/req; Kraken ~1 req/s public, IP-based.
  - Kraken: https://www.kraken.com/features/trading-api · https://support.kraken.com/articles/206548367 · CSV history: https://support.kraken.com/articles/360047124832
- **Alpaca** — free paper trading (email-only account) + free real-time (Basic = IEX for equities) + simulated crypto; API-only.
  - https://alpaca.markets/data · https://docs.alpaca.markets/us/docs/paper-trading · https://docs.alpaca.markets/us/docs/about-market-data-api
- **DuckDB / Polars / Parquet** for local time-series/finance; "DuckDB+Polars+Pandas" workflow.
  - https://duckdb.org · https://pola.rs · https://questdb.com/blog/why-parquet-matters-for-time-series-and-finance/

## UI & packaging

- **NiceGUI** — MIT; FastAPI+Vue; WebSocket live; self-hosting-first. https://nicegui.io · comparison: https://www.bitdoze.com/streamlit-vs-nicegui/
- **Streamlit** — Apache-2.0; rapid data apps; rerun model. https://streamlit.io
- **pywebview** — BSD-3 (native window). **PyTauri** — MIT+Apache-2.0; system-webview; bundles NiceGUI/FastAPI to `.exe` via `pytauri-wheel` (no Node/Rust needed).
  - https://github.com/pytauri/pytauri · https://pytauri.github.io/pytauri/
- Textual (MIT), Dash (MIT), Gradio (Apache-2.0) — evaluated, secondary/again roles.

## Research discipline (overfitting)

- **Deflated Sharpe Ratio** — Bailey & López de Prado (2014): corrects Sharpe for selection bias, multiple testing, sample length, non-normality; overfit strategies tend to *underperform* OOS.
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 · https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio
- **Probability of Backtest Overfitting (PBO)** — Bailey et al.: https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting
- **Walk-forward validation** (Pardo lineage) — rolling re-optimization; modern rigor: https://arxiv.org/pdf/2512.12924
- Dangers of backtesting overview: https://portfoliooptimizationbook.com/book/8.3-dangers-backtesting.html

## Costs (build labor)

- **Claude Code pricing** — Pro $20/mo, Max 5x $100/mo, Max 20x $200/mo; API Sonnet intro $2/$10 per MTok through Aug 31 2026, then $3/$15.
  - https://claude.com/pricing (official) · secondary summaries: finout.io, ssdnodes.com (treat as `[Likely]`, confirm on official page)

## Version control / misc

- GitHub free private repos: https://github.com/pricing
- Jupyter (BSD): https://jupyter.org

## How to refresh this map

Re-run four category searches and diff: (1) "<framework> license maintenance 2026", (2) "<data source> free tier rate limits pricing", (3) "NiceGUI/Streamlit/PyTauri packaging 2026", (4) "deflated Sharpe / PBO / walk-forward". Update the in-text `[Certain]/[Likely]/[Guessing]` tags accordingly. Anything cost- or license-sensitive should be re-checked against the **official** source before you spend money or distribute software.
