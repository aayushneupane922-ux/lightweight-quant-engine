# 17 — Claude Code Master Prompt

Paste this once at the start of a Claude Code session (or keep it as `CLAUDE.md`, see [`16`](16-mvp-build-plan.md) §16.9). It sets the mission, the rules, and the guardrails. Then run milestone prompts from [`18`](18-claude-code-milestone-prompts.md) one at a time.

---

```
You are implementing `lightweight-quant-engine`: a local-first, PAPER-TRADING-ONLY
quantitative research and paper-trading engine. Crypto-first, asset-agnostic via
adapters. You will build it in milestones. Follow this master context exactly.

MISSION
Build a lightweight, powerful, deterministic, auditable research + paper-trading engine
that a solo developer can fully understand and maintain. It must make accidental live
trading structurally impossible. It must never claim or assume profitability.

NON-NEGOTIABLE RULES (violating any is a build failure)
1.  No live trading in the MVP. No broker credentials. No real-order code paths.
    The ONLY ExecutionAdapter is PaperBroker (is_paper=True), asserted at startup.
2.  A compile-time constant LIVE_TRADING_ENABLED=False exists; there is no supported
    way to flip it. Config schema (pydantic Enums) must REJECT mode: live and any
    real execution adapter value.
3.  Every OrderIntent passes through RiskEngine.check() via exactly ONE choke-point
    function that constructs Order. No other code path may construct an Order.
4.  Strategies are deterministic: no wall-clock reads (use injected Clock), no unseeded
    RNG, no network, no I/O in the decision path. Act on a bar only AFTER it completes.
5.  Everything is event-driven and single-threaded in the decision loop. The same loop
    runs backtest (ReplayClock) and paper (WallclockClock); strategy/risk/execution code
    is identical across both.
6.  Every event is appended to a hash-chained, append-only JSONL audit log and mirrored
    to DuckDB. Runs record code git SHA + config hash + data version + seed.
7.  Do NOT research, reference, or implement Sierra Chart or DTC. Use only generic
    MarketDataAdapter / ExecutionAdapter seams. Future-adapter files are NotImplementedError stubs.
8.  Runtime dependencies must be MIT/BSD/Apache-2.0 only. No GPL, no Commons Clause in
    the runtime. vectorbt (if used at all) is for offline research ONLY, never imported by
    the engine. Never depend on Backtrader.

ARCHITECTURE (own the spine, rent the muscles)
- You WRITE: event loop, clock, event bus, order state machine, portfolio/cash accounting,
  risk engine, audit log, paper broker + fill/slippage/commission simulator, CLI.
- You WRAP behind interfaces (never leak their types): ccxt (crypto data), DuckDB/Polars/
  PyArrow/Parquet (storage), pandas-ta (indicators), QuantStats (analytics), and LATER
  skfolio/PyPortfolioOpt (portfolio), statsmodels/arch/hmmlearn/ruptures (models).
- Interfaces (Protocols in src/lqe/core): Clock, MarketDataAdapter, Strategy, Model,
  RiskEngine, ExecutionAdapter, Analytics. Contracts are specified in docs/12 and docs/05.

STACK
Python 3.12+, ccxt, duckdb+polars+pyarrow, pandas+numpy, pandas-ta, quantstats, pydantic,
NiceGUI, pytest+hypothesis, ruff+mypy, structlog. Package layout is in docs/16 §16.1.

DEFINITION OF DONE (every change)
- ruff + mypy clean; all tests green including safety (lockout), determinism (replay
  equality), risk property tests, and backtest↔paper parity tests.
- Audit log intact + hash-chain verifies. Relevant docs updated.
- New third-party runtime dep? STOP and confirm license is MIT/BSD/Apache-2.0 first.

WORKING STYLE
- Build strictly by milestone (docs/18). Do not jump ahead or add out-of-scope features
  (see docs/16 §16.7 "What NOT to build yet"). Prefer the smaller, safer option.
- For each milestone: (a) restate acceptance criteria, (b) write/adjust tests first where
  practical, (c) implement, (d) run the full suite, (e) summarize what changed and why,
  (f) STOP for my review before the next milestone.
- When a decision is ambiguous, choose determinism, safety, and simplicity over power.
- Never write code that could place a real order, hold a credential, or reach a broker.

FIRST ACTION
Read docs/05 (architecture), docs/10 (paper engine), docs/11 (risk), docs/12 (schema),
docs/16 (build plan). Then implement Milestone 1 from docs/18 and stop for review.
```

---

## How to use this prompt

1. Put the 24 spec files in a `docs/` folder in the repo and this block in `CLAUDE.md`.
2. Start the session; let Claude Code read the referenced docs.
3. Run **Milestone 1** ([`18`](18-claude-code-milestone-prompts.md)); review; then proceed one milestone at a time.
4. After any change to `risk/`, `execution/`, or `paper/`, run the **safety review prompt** ([`19`](19-claude-code-review-prompts.md)) before merging.
5. Keep the "STOP for review" discipline — it's your overfitting/scope-creep/safety checkpoint.
