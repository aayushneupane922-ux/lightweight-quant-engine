# 20 — Final Decision Log

Each decision: what was decided, why, alternatives rejected, confidence, and what would change it. This is the record Claude Code should treat as settled unless you revise it.

| # | Decision | Rationale | Rejected alternatives | Confidence | Revisit if… |
|---|---|---|---|---|---|
| D1 | **Custom event-driven core** as MVP engine | Easiest way to guarantee determinism, risk-gate-on-every-order, replay, and live-lockout; smallest surface a solo dev can own; best Claude Code determinism | LEAN (Docker, C#, heavy), Nautilus (Rust learning curve, LGPL), Backtrader (unmaintained/GPL) | High | You need multi-asset live execution or institutional throughput sooner than expected |
| D2 | **Adopt libraries, not engines** | Permissive libs (ccxt/DuckDB/pandas-ta/QuantStats) give power without lock-in, behind interfaces | Building on a mega-framework | High | A library becomes unmaintained → swap behind its adapter |
| D3 | **Crypto-first, asset-agnostic core** | Free real-time + historical public data (no key), 24/7; adapters keep equities/futures/Sierra pluggable | Equities-first (paywalled real-time), futures-first (expensive data) | High (your choice) | You commit to equities/futures as the real target |
| D4 | **$0 data/compute path; Claude Code is the only cost** | Every runtime component has a free path; crypto public APIs suffice for research+paper | Paid data in MVP | High | You graduate a strategy to serious paper trading (buy clean data) |
| D5 | **NiceGUI for MVP UI**, pywebview→PyTauri for the Windows window | App-style, WebSocket-live, MIT, self-hosting; packages to a desktop `.exe` | Streamlit (rerun model fights live views), React (overkill), Dash/Gradio | Medium-High | UI becomes a multi-user product (then consider React) |
| D6 | **Paper-only; live absent, not disabled** | Structural safety (constraints #1/#2); you can't misfire what you didn't build | "Disabled live mode" (too easy to flip) | High | Never, for the MVP. Post-MVP only behind professional-review gates |
| D7 | **Deterministic strategies only; no RL/LLM in the loop** | Constraints #3/#4; RL/LLM are non-deterministic, overfitting-prone, unvalidatable for a solo dev | FinRL/TensorTrade, LLM signals | High | You have rock-solid infra + discipline and accept heavy skepticism |
| D8 | **MVP models = trend, mean-reversion, TS-momentum (+ execution & sizing)** | Deterministic, single-asset, OHLCV-only, easiest to validate honestly | Factor/pairs/ML/portfolio-opt in MVP | High | After infra proven, add pairs/portfolio/ML as *later* milestones |
| D9 | **Research protocol is the real product** | Overfitting/look-ahead is the top failure mode; DSR/PBO/walk-forward/kill-criteria are the safeguard | "Just backtest and trust the Sharpe" | High | Never abandon; strengthen (add CPCV) as you scale |
| D10 | **Storage = Parquet + DuckDB (+Polars)** | Local, fast, zero-server, portable; strong for time-series | Cloud DB, CSV-only, SQLite-only | High | Data outgrows a single machine (unlikely at MVP scale) |
| D11 | **Risk engine = single hard gate, fail-closed** | Constraint #5; one choke point is provable and testable | Distributed/advisory checks | High | Never weaken; only add rules |
| D12 | **vectorbt research-only; never in runtime** | Commons Clause + it's not an execution engine + overfitting risk | vectorbt as the engine | High | You buy vectorbt PRO for research (still not the runtime) |
| D13 | **NautilusTrader as the future graduation engine** | Best long-term event-driven/deterministic/live-ready engine; adapter seam now | LEAN as graduation (Docker/C#) | Medium | You hit the custom core's limits and need live multi-venue |
| D14 | **Sierra/DTC deliberately excluded** | Your instruction; keep generic seams only | Researching Sierra now | High (your instruction) | You start the separate Sierra research track |
| D15 | **Build M1 + safety tests before any strategy** | Prove safe+deterministic before the system can act | Strategy-first | High | Never reorder |
| D16 | **Claude Code Pro ($20) to start** | Enough for paced solo build; upgrade only if limited | Start on Max (overpay), API (pricier for heavy use) | Medium | Multi-hour sprints hit limits → Max 5x temporarily |

## Settled defaults (so Claude Code doesn't re-litigate)

- Language: Python 3.12+. Timestamps: UTC, left-edge bars, act-after-completion.
- Accounting: cash-only, no leverage, explicit precision.
- Fills: pessimistic (next-bar-open default). Costs modeled always; cost-sensitivity sweep mandatory.
- Audit: append-only JSONL, hash-chained, mirrored to DuckDB.
- Tests: unit + property + parity + safety + data; CI runs all + ruff + mypy + license gate.
- UI: localhost only, no auth, no remote exposure, cannot construct orders.

## Open decisions deferred to you (not blockers for MVP)

- Which exchange(s) to standardize on first (Binance vs. Kraken vs. Coinbase) — see [`22`](22-unanswered-questions.md).
- Your own code license (MIT vs. proprietary) — only matters at distribution.
- Whether to ever pursue live trading — a separate, gated decision with professional review.

*Full reasoning behind each decision lives in the referenced files; the challenge to these decisions is in [`21-red-team-review.md`](21-red-team-review.md).*
