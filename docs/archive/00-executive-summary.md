# 00 — Executive Summary

**Project:** `lightweight-quant-engine`
**Date:** 2026-07-02
**Author role:** Senior quant-systems architect / quant researcher / trading-systems safety reviewer / open-source evaluator / Claude Code implementation planner
**Status:** Research + master plan. **No code is built in this document.**

> **Disclaimer.** This is research, engineering, and risk-management planning. Nothing here is a prediction of profit, investment advice, legal advice, tax advice, or accounting advice. No strategy in this plan is claimed to be profitable. The plan is optimized for *testability, falsifiability, safety, and low cost* — not returns.

---

## The one-paragraph answer

Build a **custom, lightweight, event-driven Python engine** that you own end-to-end, and consume the open-source quant ecosystem as **libraries behind adapter interfaces**, not as an engine you inherit. Validate everything on **free crypto public market data** (via `ccxt`) with an **asset-agnostic core** so equities/futures/Sierra can plug in later. Ship a **local desktop-window UI** (NiceGUI served on localhost, later wrapped with pywebview/PyTauri into a Windows `.exe`). The system is **paper-trading only** in the MVP, with a hard, structurally-enforced **live-trading lockout**. The only meaningful recurring cost is your **Claude Code subscription** ($20–$200/mo depending on plan); the data, storage, compute, UI, and analytics layers can all be **$0** ([Claude pricing](https://claude.com/pricing)).

---

## Confidence-tagged headline recommendations

- **[Certain] Do not build on Backtrader.** It is effectively unmaintained ("archive mode," no PyPI release in 12+ months) and GPL-3.0. ([Is Backtrader dead? — community thread](https://community.backtrader.com/topic/3702/is-backtrader-dead))
- **[Certain] Do not make vectorbt (open-source) your product engine.** Its open edition is Apache-2.0 **+ Commons Clause**, which forbids selling a product/service that is "primarily this software." Fine for private research; risky as the core of a distributed Windows product. ([vectorbt license](https://vectorbt.dev/terms/license/))
- **[Likely] Custom engine beats adopting LEAN or NautilusTrader for *this* MVP.** LEAN requires Docker for local runs (extra complexity for a solo dev) ([lean-cli](https://github.com/QuantConnect/lean-cli)); NautilusTrader is powerful but has a steep Rust-core learning curve and LGPL-3.0 licensing to reason about ([Nautilus licensing](https://nautilustrader.io/legal/open-source-licensing/)). Your non-negotiables (deterministic replay, risk-gate-on-every-order, kill switch, no accidental live path) are *easier to guarantee in ~2–4k lines you control* than by bending a large framework.
- **[Likely] NautilusTrader is the best long-term "graduation" engine** if you outgrow the custom core — design a `NautilusExecutionAdapter` seam now, don't adopt it now.
- **[Certain] A $0/month data path exists** for crypto research + paper trading using exchange public REST/WebSocket endpoints (no API key needed for public market data) ([Binance/Kraken/Coinbase public APIs](https://docs.kraken.com/)). "$0 reliable real-time equities/futures" does **not** exist — that is a future paid decision point.
- **[Certain] Reinforcement learning and LLM-in-the-loop trading are out of scope for the MVP** — they violate your own constraints (deterministic, testable, no autonomous LLM decisions) and are overfitting magnets for a solo dev.

---

## The recommended MVP stack (one glance)

| Layer | Choice | License | Why |
|---|---|---|---|
| Language/runtime | Python 3.12+ | PSF | Ecosystem gravity; Claude Code fluency |
| Engine | **Custom event-driven core** | yours | Determinism, replay, risk gate, lockout |
| Market-data adapter | **`ccxt`** (crypto) + CSV replay | MIT | 100+ exchanges, free public data ([ccxt](https://github.com/ccxt/ccxt)) |
| Storage | **Parquet + DuckDB** (+ Polars) | MIT / MIT / MIT | Local, fast, zero-server ([DuckDB](https://duckdb.org)) |
| Indicators | **pandas-ta** (TA-Lib optional) | MIT | Pure-python, no C build on Windows |
| Portfolio math (later) | **skfolio** / PyPortfolioOpt | BSD-3 / MIT | sklearn-native HRP/BL/MVO |
| Models (later) | statsmodels, arch, hmmlearn, ruptures | BSD/permissive | Pairs, GARCH, regime |
| Analytics/tearsheets | **QuantStats** | Apache-2.0 | Metrics + reports |
| Research-only sweeps | **vectorbt (open)** | Apache-2.0+Commons Clause | Fast vectorized exploration, *kept out of runtime* |
| UI | **NiceGUI** (localhost) | MIT | App-style, WebSocket live updates ([NiceGUI](https://nicegui.io)) |
| Desktop packaging (later) | **pywebview** → PyTauri | BSD / MIT+Apache | "App in a window," `.exe` build ([PyTauri](https://github.com/pytauri/pytauri)) |
| Data validation | Pandera or hand-rolled checks | MIT | Schema + lookahead guards |

Full evaluation with citations: [`02-open-source-framework-matrix.md`](02-open-source-framework-matrix.md), [`15-open-source-license-review.md`](15-open-source-license-review.md).

---

## The six answers you asked for at the end

1. **Recommended MVP stack:** the table above — custom core + ccxt + Parquet/DuckDB + pandas-ta + NiceGUI, crypto data, paper-only.
2. **Cheapest serious path:** custom core + crypto public data + local compute + Claude Code **Pro ($20/mo)**. Effective non-Claude spend: **$0/mo**. (If you already pay for a Claude Max plan for other work, marginal cost ≈ $0.)
3. **Top architecture decision:** *Build the engine, adopt the libraries.* Own the event loop, order state machine, risk engine, and audit log; wrap everything else behind `MarketDataAdapter` / `ExecutionAdapter` / `Strategy` / `Model` interfaces.
4. **First Claude Code prompt to run:** the Milestone 1 prompt in [`18-claude-code-milestone-prompts.md`](18-claude-code-milestone-prompts.md) — "local-only deterministic core engine + event bus + clock + config + structural live-trading lockout," with tests. The master context prompt is [`17-claude-code-master-prompt.md`](17-claude-code-master-prompt.md).
5. **Biggest reason this could fail:** *not the engine — the research discipline.* Overfitting + look-ahead bias will make a broken strategy look brilliant, and a solo dev with a fast backtester is the ideal victim. The kill-criteria and deflated-Sharpe/PBO controls in [`09-backtesting-research-protocol.md`](09-backtesting-research-protocol.md) are the actual product.
6. **Safest next step:** implement **Milestone 1 + Milestone 9's lockout tests first** (engine skeleton + "prove live trading is structurally impossible"), before any strategy. Ship nothing that can place a real order.

---

## What to build first vs. not build

**Build first (MVP):** deterministic event core → data ingestion/validation (crypto Parquet) → backtest/replay → research analytics → paper broker (simulated fills) → NiceGUI dashboard → 3 simple deterministic strategies (trend, mean-reversion, momentum) → paper-trading daemon → safety/audit review.

**Do not build yet:** live broker integration, broker credentials, cloud deployment, RL/LLM decision models, options complexity, HFT/order-book microstructure, cross-sectional factor universes, Sierra/DTC specifics. See [`16-mvp-build-plan.md`](16-mvp-build-plan.md) §"What not to build yet."

---

## Reading order for the rest of this package

1. Decisions: [`05-recommended-architecture.md`](05-recommended-architecture.md), [`20-final-decision-log.md`](20-final-decision-log.md)
2. Money: [`06-cost-analysis.md`](06-cost-analysis.md), [`07-free-and-low-cost-plan.md`](07-free-and-low-cost-plan.md)
3. Safety: [`10-paper-trading-engine-spec.md`](10-paper-trading-engine-spec.md), [`11-risk-engine-spec.md`](11-risk-engine-spec.md), [`14-safety-risk-and-compliance-review.md`](14-safety-risk-and-compliance-review.md)
4. Build: [`16-mvp-build-plan.md`](16-mvp-build-plan.md) → [`17`](17-claude-code-master-prompt.md)/[`18`](18-claude-code-milestone-prompts.md)/[`19`](19-claude-code-review-prompts.md)
5. Challenge: [`21-red-team-review.md`](21-red-team-review.md), [`22-unanswered-questions.md`](22-unanswered-questions.md)

*Every non-trivial claim in the deeper files is cited; the full source list is [`23-appendix-source-map.md`](23-appendix-source-map.md).*
