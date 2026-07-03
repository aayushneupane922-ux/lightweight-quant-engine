# 02 — Open-Source Framework & Library Matrix

**Verified:** July 2026. Licenses/maintenance change — re-check before committing. Legend for **Verdict**: **USE** (in runtime, behind an interface) · **RESEARCH** (research/exploration only, not in the runtime engine) · **LEARN** (read the ideas/code, don't depend on it) · **AVOID** (for this MVP).

## 2.1 Summary table

| Tool | Purpose | License | Maintained (2026) | Runtime | Verdict (MVP) |
|---|---|---|---|---|---|
| **Custom engine (yours)** | Event core | — | you | Python | **USE (core)** |
| QuantConnect **LEAN** | Full backtest+live engine | Apache-2.0 | Active | C#/Python | LEARN / future adapter |
| **NautilusTrader** | Event-driven engine | **LGPL-3.0** | Active | Rust+Python | LEARN / long-term graduation |
| **Backtrader** | Backtester | **GPL-3.0** | **Unmaintained** | Python | **AVOID** |
| **vectorbt** (open) | Vectorized backtest | **Apache-2.0 + Commons Clause** | Slowed (PRO focus) | Python/Numba | **RESEARCH only** |
| **Zipline-reloaded** | Daily backtester | Apache-2.0 | Active (S. Jansen) | Python | LEARN / RESEARCH |
| **Qlib** | AI quant platform | MIT | Active (Microsoft) | Python | LEARN / later |
| **FinRL** | RL for trading | MIT | Active (academic) | Python | **AVOID (MVP)** |
| **TensorTrade / -NG** | RL env | Apache-2.0 | Low activity | Python | **AVOID (MVP)** |
| **PyPortfolioOpt** | Portfolio opt | MIT | Moderate | Python | USE (later) |
| **skfolio** | Portfolio opt (sklearn) | BSD-3 | Active | Python | USE (later, preferred) |
| **riskfolio-lib** | Portfolio/risk opt | BSD-3 | Active | Python/cvxpy | USE (later, alt) |
| **QuantStats** (+ -reloaded) | Tearsheets/metrics | Apache-2.0 | Active (fork) | Python | **USE** |
| **empyrical** (+ -reloaded) | Risk metrics | Apache-2.0 | Orig. stale; fork active | Python | USE (via fork) |
| **pandas-ta** (+ -classic) | Indicators | MIT | Gaps; fork active | Python | **USE** |
| **TA-Lib** | Indicators (C) | BSD-3 | Active binding | C+Python | Optional (build burden) |
| **ccxt** | Crypto exchange API | MIT | Very active | Python+ | **USE (data adapter)** |
| **DuckDB** | Embedded OLAP SQL | MIT | Very active | C++/Python | **USE (storage)** |
| **Polars** | DataFrame engine | MIT | Very active | Rust/Python | **USE** |
| **pandas** | DataFrames | BSD-3 | Very active | Python | USE |
| **NumPy** | Arrays | BSD-3 | Very active | C/Python | USE |
| **Numba** | JIT | BSD-2 | Active | Python/LLVM | USE (hot loops only) |
| **PyArrow** | Columnar/Parquet | Apache-2.0 | Very active | C++/Python | USE |
| **statsmodels** | Econometrics | BSD-3 | Active | Python | USE (later, pairs/regime) |
| **arch** | GARCH/vol | NCSA (permissive) | Active (bashtage) | Python | USE (later, vol) |
| **hmmlearn** | HMM regimes | BSD-3 | Active | Python | USE (later, regime) |
| **ruptures** | Change-point | BSD-2 | Active | Python | USE (later, regime) |
| **NiceGUI** | Local app UI | MIT | Active | Python | **USE (UI)** |
| **Streamlit** | Data app UI | Apache-2.0 | Active (Snowflake) | Python | USE (research reports) |
| **pywebview** | Native window | BSD-3 | Active | Python | USE (packaging) |
| **PyTauri** | Native shell/.exe | MIT+Apache-2.0 | New, active | Rust/Python | USE (packaging, later) |

---

## 2.2 Detailed evaluations (the engines/frameworks — the hard calls)

### QuantConnect LEAN
- **Purpose:** full-featured algorithmic-trading engine: backtesting, optimization, paper & live trading, many asset classes.
- **License:** Apache-2.0 — permissive, free for commercial use, no copyleft. ([LICENSE](https://github.com/QuantConnect/Lean/blob/master/LICENSE), [lean.io](https://www.lean.io/))
- **Maintenance:** active, commercially backed by QuantConnect.
- **Runtime/maturity:** C# core with a Python API; very mature; multi-asset; runs Windows/Mac/Linux.
- **Backtesting / paper / live:** all first-class (live is **out of scope** for you).
- **Complexity / integration burden:** **high for a solo dev.** Local runs depend on **Docker** (LEAN executes in a Linux container) — a real added-complexity tax you specifically don't want. ([lean-cli](https://github.com/QuantConnect/lean-cli), [docs](https://www.lean.io/docs/v2/lean-cli/key-concepts/getting-started))
- **Lock-in risk:** moderate — its data/algorithm abstractions are opinionated; deep use couples you to LEAN's model of the world.
- **Solo-dev suitability:** moderate. Powerful, but you'd spend your budget learning LEAN, not your domain.
- **Claude Code suitability:** moderate — large C#/Python surface; Claude Code can drive it but the Docker + framework conventions add friction and non-determinism at the infra layer.
- **Verdict:** **LEARN** its data/universe/algorithm abstractions; keep a **future `LeanExecutionAdapter`** as an option. Not the MVP core.

### NautilusTrader
- **Purpose:** high-performance, **deterministic, event-driven** trading platform + backtester; "production-grade Rust-native." ([GitHub](https://github.com/nautechsystems/nautilus_trader))
- **License:** **LGPL-3.0.** Using it as an unmodified library (dynamic linking) is generally fine even in a commercial/closed app, but *modifying Nautilus itself* triggers copyleft on those modifications, and shipping a bundled `.exe` warrants care. ([Nautilus licensing](https://nautilustrader.io/legal/open-source-licensing/))
- **Maintenance:** active, copyright through 2026.
- **Runtime/maturity:** Rust core + Python API; mature and fast; **pip-installable without Docker** (advantage over LEAN for solo devs). ([install docs](https://nautilustrader.io/docs/latest/getting_started/installation/))
- **Backtesting / paper / live:** all first-class; strong determinism story (aligns with your replay requirement).
- **Complexity / learning curve:** **steep.** Rust-core concepts, actor/message model, and a large API. More than a solo MVP needs on day one.
- **Lock-in risk:** moderate–high (its event/actor model is the whole point; you'd design around it).
- **Solo-dev suitability:** good *once you've grown*; heavy for a first MVP.
- **Claude Code suitability:** moderate — Python API is scriptable, but the concept count is high and the Rust core is opaque to quick iteration.
- **Verdict:** **LEARN** its event/determinism design (borrow the ideas). **Best long-term graduation engine** — design a `NautilusExecutionAdapter` seam, adopt later only if the custom core hits its limits.

### Backtrader
- **Purpose:** popular Python backtester (and some live).
- **License:** **GPL-3.0** — strong copyleft; complicates shipping closed/commercial Windows software.
- **Maintenance:** **effectively unmaintained** — "archive mode," no PyPI release in 12+ months; creator considers it complete; community forks (`backtrader_next`, `-slim`, `cloudQuant/backtrader`) exist but are fragmented. ([Is Backtrader dead?](https://community.backtrader.com/topic/3702/is-backtrader-dead), [maintenance thread](https://community.backtrader.com/topic/2466/backtrader-maintenance))
- **Verdict:** **AVOID.** Unmaintained + GPL + slower runtime = wrong foundation for new work. Its clean strategy/indicator API is worth reading once for design inspiration, nothing more.

### vectorbt (open-source edition)
- **Purpose:** extremely fast **vectorized** backtesting — run thousands of parameter combinations quickly.
- **License:** **Apache-2.0 + Commons Clause.** You may use it for free, but you **may not sell a product/service that is primarily this software.** ([license](https://vectorbt.dev/terms/license/), [repo](https://github.com/polakowo/vectorbt))
- **Maintenance:** open edition maintenance has slowed in favor of the commercial **vectorbt PRO** (~$20/mo). ([PRO](https://vectorbt.pro/))
- **Strengths / traps:** blazing sweeps; but vectorized backtesting **hides look-ahead bias and path dependence** if misused, and its "test thousands of ideas" superpower is exactly how solo devs overfit.
- **Verdict:** **RESEARCH ONLY.** Great for offline hypothesis screening; **keep it out of the runtime/paper engine** (Commons Clause + lock-in + it's not an execution engine). Anything it finds must be re-validated in *your* event-driven backtester with realistic costs.

### Zipline-reloaded
- **Purpose:** Pythonic daily backtesting library (the maintained fork of Quantopian's Zipline).
- **License:** Apache-2.0. **Maintenance:** active — Stefan Jansen shipped 3.1.1 for Python 3.13 / NumPy 2.0. ([repo](https://github.com/stefan-jansen/zipline-reloaded), [ml4trading](https://x.com/ml4trading/status/1948303607729631620))
- **Fit:** built around **daily US-equity bundles**; awkward for intraday crypto; bundle ingestion is fiddly.
- **Verdict:** **LEARN / RESEARCH.** Excellent to study (and pairs with the *ML for Trading* book), but not a natural fit for crypto-first intraday. Don't make it the core.

### Qlib (Microsoft)
- **Purpose:** AI-oriented quant **research** platform (supervised learning, market-dynamics modeling, RL; now tied to RD-Agent for automated R&D). ([repo](https://github.com/microsoft/qlib))
- **License:** MIT. **Maintenance:** active.
- **Fit:** powerful for **cross-sectional equity ML factor research** with a data-server model; heavy and opinionated; overkill for a lightweight crypto MVP.
- **Verdict:** **LEARN / later.** Revisit if you move into ML factor research on equities. Not MVP.

### FinRL / TensorTrade(-NG)
- **Purpose:** reinforcement-learning frameworks for trading. FinRL is MIT and active (academic; next-gen "FinRL-X"). ([FinRL](https://github.com/AI4Finance-Foundation/FinRL)) TensorTrade is Apache-2.0 with low recent activity.
- **Fit / traps:** RL trading is **non-deterministic to train, brutal to validate, and a top overfitting/instability risk** for a solo dev. It also conflicts with your constraints (#3 no autonomous opaque decisions in spirit, #4 deterministic strategies).
- **Verdict:** **AVOID for MVP.** Revisit only after you have rock-solid data, backtest discipline, and paper-trading infrastructure — and even then, with skepticism.

---

## 2.3 Libraries you should USE (behind interfaces)

- **ccxt (MIT)** — unified API for 100+ crypto exchanges; REST + WebSocket; your `CcxtMarketDataAdapter`. Free public market data, no key. ([ccxt](https://github.com/ccxt/ccxt), [docs](https://docs.ccxt.com/))
- **DuckDB (MIT) + Polars (MIT) + PyArrow (Apache-2.0) + Parquet** — the local research/storage stack: DuckDB for relational queries over Parquet, Polars for fast transforms, Arrow for zero-copy exchange. No server, no cloud. ([DuckDB](https://duckdb.org), [Polars](https://pola.rs))
- **pandas-ta (MIT)** — pure-Python indicators; no C build on Windows. `pandas-ta-classic` fork is actively maintained if the original stalls. TA-Lib (BSD-3) is faster but needs a C library build — **optional**, behind the same indicator interface.
- **QuantStats (Apache-2.0)** — tearsheets, drawdown, Sharpe/Sortino, and metrics for your research reports. Use `quantstats-reloaded` if you need current Python compatibility.
- **skfolio (BSD-3)** / **PyPortfolioOpt (MIT)** / **riskfolio-lib (BSD-3)** — portfolio optimization (MVO, Black-Litterman, HRP). **skfolio** preferred for its sklearn-native cross-validation and stress-testing API. ([skfolio](https://github.com/skfolio/skfolio)) *(later milestone)*
- **statsmodels (BSD-3)** — ADF/cointegration for pairs; **arch** — GARCH/vol; **hmmlearn (BSD-3)** & **ruptures (BSD-2)** — regime detection. *(later milestone)*

## 2.4 Cross-cutting evaluation notes

- **License risk concentration:** the only real traps are **Backtrader (GPL-3.0, avoid)**, **vectorbt (Commons Clause, research-only)**, and **NautilusTrader (LGPL-3.0, handle deliberately)**. Everything you'd put in the runtime is MIT/BSD/Apache-2.0 — clean for a distributed Windows product. Full analysis: [`15`](15-open-source-license-review.md).
- **Lock-in defense:** every third-party library sits behind one of your interfaces (`MarketDataAdapter`, `Indicator`, `PortfolioOptimizer`, `Analytics`). Swapping ccxt for a broker feed, or pandas-ta for TA-Lib, is a one-file change.
- **Solo-dev + Claude Code suitability:** the winning pattern is *small owned core + permissive libraries*, which maximizes both. Large frameworks (LEAN/Nautilus) reduce Claude Code determinism because much behavior lives in framework internals you don't control.
