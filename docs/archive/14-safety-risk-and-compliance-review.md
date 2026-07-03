# 14 — Safety, Risk & Compliance Review

> **Not legal, financial, tax, or accounting advice.** This is an engineering safety review plus a list of questions to take to qualified professionals *before* any future live trading. When in doubt, consult a licensed professional in your jurisdiction.

## 14.1 Threat model (what could go wrong, MVP scope)

| Risk | Consequence | Mitigation (built in) |
|---|---|---|
| **Accidental live trading** | Real money at risk | Live path **absent**, not just disabled: no broker SDK, no credentials, `is_paper` startup assertion, config schema rejects `live`, tests forbid order-network paths (§14.6) |
| **Paper/live mismatch** | Backtest/paper flatters vs. reality | Pessimistic fills, cost-sensitivity sweeps, parity tests; *treat paper as optimistic* |
| **Overfitting / look-ahead** | Confidently trading a lie | Research protocol [`09`](09-backtesting-research-protocol.md): DSR/PBO, walk-forward, kill-criteria |
| **Automation failure / runaway loop** | Order storms, wrong state | Max order rate/count, kill switch, reconciliation, fail-closed risk gate |
| **Stale / bad data** | Trading on frozen/garbage feed | Stale-data guard (no trade), data-quality checks, cross-source spot checks |
| **State corruption / crash** | Wrong positions/PnL | Append-only audit, hash chain, rebuild-from-audit + reconcile on restart |
| **Credential leak** | Account compromise | **No credentials in MVP**; when added later, OS keychain + never in repo/logs |
| **Local machine compromise** | Data/artifact tampering | Localhost-only UI, no exposed ports, audit hash-chain, backups |

## 14.2 Paper vs. live mismatch (know the limits of paper)

Even a good paper simulator omits: real queue position, partial-fill dynamics, market impact, latency variance, exchange outages during *your* order, funding/borrow, and slippage in fast markets. **Paper results are an optimistic upper bound.** Never reason "it worked in paper, so live will match." This is a headline reason live trading is deliberately out of MVP scope.

## 14.3 Data licensing & exchange restrictions (do not hand-wave)

- **Crypto public APIs** are free for market data but have **Terms of Service**: rate limits, and often **redistribution restrictions**. Keep data **local**; do **not** republish or resell exchange data. Read each exchange's API terms. ([Kraken API](https://www.kraken.com/features/trading-api))
- **yfinance / unofficial sources:** convenient but ToS-gray; fine for private research, **not** for redistribution or as a reliability-critical feed.
- **Vendor data (later):** paid feeds carry explicit license terms (per-user, non-redistribution, display rules). Review before building anything user-facing on them.
- **Rule:** the data adapter keeps all raw data local and versioned; no component ships or exposes third-party market data externally.

## 14.4 Broker terms & automation (for the future, not MVP)

Before ANY live connection (out of scope now), you must understand: API/automation permissions, rate limits, order-type support, PDT and similar rules, market-data entitlements/fees, and liability for automated errors. The `ExecutionAdapter` seam exists so this is a *future, deliberate, reviewed* step — never an accident.

## 14.5 Kill-switch design (safety-critical)

- One-click from UI; also a file flag + CLI so it works even if the UI is down.
- Persisted to disk; **auto-clears never** (only explicit operator action).
- Checked before every order and every loop tick.
- Triggers: manual, daily-loss breach, max-DD breach, reconciliation failure, repeated data-staleness.
- On kill: stop new orders, cancel working, optional FLATTEN, loud audit entry.
- Tested: once killed, no risk-increasing order can be emitted (property test).

## 14.6 Avoiding accidental live-order paths (defense in depth)

1. **Absence over disable:** no real-broker code in the repo (only a `NotImplementedError` stub).
2. **Startup invariant:** engine refuses to run unless `execution_adapter.is_paper is True`.
3. **Compile-time constant:** `LIVE_TRADING_ENABLED = False`, no supported flip in MVP.
4. **Schema rejection:** config `mode`/`execution.adapter` enums exclude live/real values.
5. **Single choke point:** only one function creates `Order`, and it calls the risk gate first.
6. **CI guards:** tests assert (a) only `PaperBroker` implements `ExecutionAdapter`; (b) no import of broker SDKs/`ccxt` *trading* methods (create_order etc.) anywhere in the engine; (c) no network egress can submit an order. See review prompts [`19`](19-claude-code-review-prompts.md).
7. **UI can't order:** UI issues only whitelisted control commands, never order payloads.

## 14.7 Audit logging & recordkeeping

- Append-only JSONL, hash-chained (tamper-evident), mirrored to DuckDB for query.
- Records every event, decision (incl. APPROVEs and REJECT reasons), and control action.
- Enables: daily reports, reconciliation, deterministic replay, and "why did/didn't this trade?" forensics.
- Keep runs/audit backed up. Good recordkeeping now is the habit you'll need if you ever go live (tax lots, trade records).

## 14.8 Credential handling (future)

MVP has **no credentials**. When a real feed/broker is added later: use the OS keychain / a secrets manager, never commit secrets, never log them, scope keys minimally (read-only where possible), and keep paper and live keys physically separate. Add a pre-commit secret scanner.

## 14.9 Local security

- UI bound to `127.0.0.1` only; no remote exposure; no auth needed *because* nothing is reachable.
- If you ever expose the UI, that's a new threat model (auth, TLS, hardening) — out of MVP scope; don't do it casually.
- Keep the machine patched; back up `data/`, `runs/`, and `catalog.duckdb`.

## 14.10 Human-in-the-loop & disclaimers

- **No autonomous LLM decisions** (constraint #3): Claude Code helps *build* the system; it is never in the trading decision loop. Strategies are deterministic Python.
- A human reviews every strategy's graduation to paper ([`09`](09-backtesting-research-protocol.md) §9.8) and every future step toward live.
- Ship an in-app disclaimer: *research/paper-trading tool; no profitability implied; not advice.*

## 14.11 When to consult a professional

Before you: connect a live broker, trade real capital, take on other people's money (this triggers serious regulation — likely a hard stop for a solo hobby project), redistribute data, or treat trading income/losses for tax. These are professional-review gates, not DIY steps.

## 14.12 Pre-live checklists — questions to ask professionals (before any live trading)

**To a broker:**
- Do your API terms permit automated/algorithmic order entry for retail? Any approval needed?
- Order types, rate limits, and throttling? What happens on limit breach?
- Market-data entitlements/fees for automated use? Real-time vs. delayed?
- PDT/similar rules for my account type and jurisdiction?
- Who is liable for erroneous automated orders? Is there a test/sandbox environment?
- Kill-switch / cancel-on-disconnect support?

**To a data vendor:**
- Exact license: per-user? redistribution? display vs. non-display? derived-data rights?
- Coverage, corporate-action handling, point-in-time correctness, and history depth?
- Uptime SLA, rate limits, and support?
- Cost triggers (symbols, request volume, real-time vs. delayed)?

**To an accountant / tax professional:**
- How are trading gains/losses treated in my jurisdiction (incl. crypto)? Wash-sale/equivalent rules?
- What records must I keep, and in what form? (Your audit log helps.)
- Do I need to register anything to trade my own capital? Thresholds?

**To a lawyer:**
- Regulatory implications of automated trading of **my own** money vs. **others'** money (the latter likely requires registration/licensing).
- Distribution of the software: license compliance (LGPL/Commons Clause — see [`15`](15-open-source-license-review.md)), liability, and disclaimers if others use it.
- Data ToS compliance for anything I redistribute or expose.

> **Bottom line:** the MVP is engineered so that the *only* thing that can happen is research and simulated trading. Everything with real-world risk — money, credentials, data redistribution, other people's capital — is behind a deliberate, professionally-reviewed gate that the MVP does not open.
