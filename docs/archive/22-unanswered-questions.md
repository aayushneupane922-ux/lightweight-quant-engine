# 22 — Unanswered Questions, Top Risks & Verify-Before-Spending

## 22.1 Top 20 risks (ranked; R1 = highest)

| # | Risk | Type | Mitigation | Owner |
|---|---|---|---|---|
| R1 | **Overfitting / look-ahead** makes a broken strategy look great | Research | DSR/PBO, walk-forward, cost sweeps, kill-criteria ([`09`](09-backtesting-research-protocol.md)) | You + research-methodologist agent |
| R2 | **Subtle backtester bugs** (bar-timing, fill look-ahead) inflate results | Engineering | Bar-completeness rule + tests, pessimistic fills, parity tests; personally audit | You |
| R3 | **Accidental live trading** (future) | Safety | Live absent-not-disabled, `is_paper` assert, schema reject, CI safety tests ([`14`](14-safety-risk-and-compliance-review.md)) | safety-reviewer agent |
| R4 | **Scope creep / never shipping** (10 milestones) | Project | Thin slice M1→M3→M6 first; review gates; "what NOT to build" list | You |
| R5 | **Custom-engine reinvention** goes framework-shaped | Engineering | Bounded scope, delegate to libraries, architecture review ([`19`](19-claude-code-review-prompts.md)) | architect agent |
| R6 | **Free crypto data is dirty** (wash volume, gaps, outages) | Data | Validation lab (M2), cross-exchange checks, treat as engineering not alpha | data-quality agent |
| R7 | **Motivation collapse from high kill-rate** | Human | Reframe: engine+process is the deliverable; killing is success | You |
| R8 | **Claude Code introduces non-determinism** (RNG/wall-clock/dict-order) | Engineering | Determinism tests, replay equality in CI | test-author agent |
| R9 | **Exchange ToS / rate-limit changes** break the free data path | External | Adapter isolates it; keep data local; multi-exchange fallback | You |
| R10 | **Paper→live false confidence** if you later go live | Safety | Explicit "paper is optimistic"; professional-review gates | You |
| R11 | **License creep** (a dep adds Commons Clause/GPL) | Legal | CI `pip-licenses` gate; forks behind interfaces | license-auditor agent |
| R12 | **Accounting drift** (float precision) | Engineering | Decimal/explicit precision, per-bar reconciliation | You |
| R13 | **Data-source outage mid-paper-session** | Ops | Stale-data guard → no trade; timeouts; audit | daemon |
| R14 | **Kill switch fails when UI is down** | Safety | File-flag + CLI kill path independent of UI | You |
| R15 | **Claude Code cost overrun** during heavy sprints | Cost | Start Pro; upgrade Max only during sprints, revert | You |
| R16 | **Strategy capacity illusion** (works only at toy size) | Research | Capacity/liquidity checks in protocol | research agent |
| R17 | **NiceGUI learning friction** slows the UI | Project | Fallback: Streamlit reports + Textual/CLI monitor | You |
| R18 | **Wrong first market** (crypto) vs. real goal (futures) | Strategy | Asset-agnostic core; adapters; revisit D3 | You |
| R19 | **Regime dependence** — edge exists only in one market regime | Research | Multi-regime walk-forward; document failure prediction | research agent |
| R20 | **Backup/data-loss** of runs/audit/catalog | Ops | Back up `data/`, `runs/`, `catalog.duckdb`; audit is append-only | You |

## 22.2 Top 20 unanswered questions (decide or verify)

**Strategy / scope**
1. Is your *real* long-term target crypto, equities, or **futures** (via Sierra later)? This changes data spend and eventual execution. (D3/D18)
2. Discretionary vs. fully-systematic end state? (Affects how much UI/decision-support vs. automation you build.)
3. Are you optimizing to *learn quant engineering*, to *find an edge*, or to *support discretionary trading*? Different success metrics.

**Data**
4. Which exchange to standardize on first — Binance (deepest data, weight limits), Kraken (CSV history, 1 req/s), or Coinbase (US-friendly, 300 rows/req)? ([APIs](https://docs.kraken.com/))
5. Spot only, or eventually perps/funding? (Perp funding is a later data type.)
6. How much history do you actually need for your timeframes, and does the free rate limit make pulling it painful?
7. When (if ever) will you need *equities* data, triggering a paid feed? (D4 trigger)

**Engineering**
8. Long/short or long/flat in MVP? (Affects accounting + risk rules.)
9. Single-strategy or multi-strategy portfolio in MVP? (Affects sizing + per-strategy budget.)
10. Timeframe focus (1m intraday vs. 1h/1d swing)? Drives data volume + fill realism needs.
11. Do you want the desktop `.exe` packaging in the MVP, or is `python -m` fine initially? (pywebview/PyTauri is otherwise deferred.)

**Cost / tooling**
12. Which Claude Code plan will you run (Pro $20 vs. Max)? Do you already pay for one? (D16 — marginal cost may be $0.) ([pricing](https://claude.com/pricing))
13. Will you ever *distribute* the app (triggering code-signing + license review), or is it personal-only?

**Research discipline**
14. What kill-rate will you emotionally accept before you're tempted to loosen criteria? (Pre-commit it.)
15. Who reviews strategy graduation — just you, or the research-methodologist agent as a gate?

**Future / live (out of MVP scope, but decide the trigger)**
16. What *specific evidence* would make you consider live trading at all? Write it now, before you're excited by a backtest.
17. Which broker would you even use, and do its terms permit retail automation? (Ask before building anything.)
18. Are you clear that trading *others'* money likely triggers registration/licensing (a hard stop)? ([`14`](14-safety-risk-and-compliance-review.md) §14.11)
19. Tax treatment of crypto/trading in your jurisdiction — who advises you? (Pre-live gate.)
20. Sierra/DTC research — when does that separate track start, and does it change the execution-adapter contract? (D14)

## 22.3 What must be verified BEFORE spending more money

Pin these down before any spend beyond the Claude Code subscription:

1. **Confirm the $0 crypto data path actually meets your needs** — pull real history for your target symbols/timeframes and run the validation lab. If free data is too gappy for your timeframe, *that's* the moment to price a paid feed — not before.
2. **Re-verify Claude Code pricing/limits for your usage** on the official page (it drifts, and intro API pricing runs only through Aug 31 2026). ([pricing](https://claude.com/pricing))
3. **Prove the engine + discipline on free data first.** Don't buy data, a code-signing cert, or vectorbt PRO until a strategy has *survived* the free-data research protocol. Paying earlier buys nothing.
4. **Re-check licenses at build time** (they change) — run the CI license gate before assuming the runtime is clean for any distribution. ([`15`](15-open-source-license-review.md))
5. **Get professional review before ANY live-trading spend** (broker, real data feeds, capital). The pre-live checklists ([`14`](14-safety-risk-and-compliance-review.md) §14.12) are the gate. Spending on live infrastructure before this review is the most expensive possible mistake.

> **One-line rule:** spend money only at the documented triggers ([`07`](07-free-and-low-cost-plan.md) §7.3), and only after the thing you'd spend on is *proven necessary* by work you already did for free.
