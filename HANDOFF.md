# HANDOFF — `lightweight-quant-engine`

**Purpose of this file:** orient a developer (human or a fresh Claude Code session) who is picking up this project cold. Read this first, then `GETTING-STARTED.md`, then `CLAUDE.md`.

## 1. What you're inheriting
A complete **research and implementation-planning package** for a lightweight, local-first, **paper-trading-only** quant engine. This is a *master plan*, not code. Your job is to implement it, milestone by milestone, without inventing new architecture.

- **Status:** design complete; **zero product code written yet**.
- **First deliverable:** Milestone 1 (deterministic core + structural live-trading lockout).
- **No live trading, no credentials, no Sierra/DTC** — see the absolute rules in `CLAUDE.md`.

## 2. Confirmed product constraints (already decided — do not re-litigate)
- **Crypto-first, asset-agnostic core** — validate on free crypto public data; equities/futures plug in later via adapters.
- **Local app in a desktop window** — NiceGUI on localhost, later wrapped to a Windows `.exe`. Not a web SaaS.
- **$0/month** for data/compute/UI — only cost is the Claude Code subscription.
- **Paper trading only.** Deterministic strategies only. No autonomous LLM/RL decisions.

Full rationale for every decision: `docs/20-final-decision-log.md`.

## 3. Document map (what's in the box)
The `docs/` folder has 24 numbered files + a README. Grouped:

- **Orient / decide:** `00` executive summary · `05` recommended architecture · `20` decision log · `21` red-team review.
- **Money:** `06` cost analysis · `07` free/low-cost plan.
- **Safety-critical specs:** `10` paper-trading engine · `11` risk engine · `14` safety/compliance · `15` license review.
- **Reference specs:** `08` data strategy · `12` event & storage schema · `13` UI spec.
- **Research discipline:** `09` backtesting protocol — **read before writing any strategy**; it's the real product.
- **Evaluations:** `02` framework matrix · `03` model taxonomy · `04` architecture options.
- **Build package:** `16` MVP build plan · `17` master prompt · `18` milestone prompts · `19` review prompts.
- **Open items:** `22` unanswered questions + top-20 risks · `23` source map · `01` research method.

## 4. The build path (10 milestones)
1. Local-only core engine (+ live lockout) ← **start here**
2. Data ingestion & validation (crypto → Parquet/DuckDB)
3. Backtesting / replay (+ paper broker & fills)
4. Research analytics (QuantStats + experiment registry)
5. Paper broker hardening (risk gate, kill switch, reconciliation)
6. Lightweight UI (NiceGUI)
7. Model-library integration (behind interface)
8. Paper-trading daemon (wall-clock, kill switch, daily report)
9. Safety & audit review (lockout/risk/parity tests + license CI gate)
10. Future adapter spike (guarded stubs; **no Sierra research**)

Exact, copy-pasteable prompts for each: `docs/18-claude-code-milestone-prompts.md`.

**Recommended first release (thin slice):** Milestones 1 → 3 → 6 (core → backtest → minimal UI), then fill in 4/5/7/8. This de-risks "never shipping."

## 5. The non-negotiable safety gates (must hold at every milestone)
1. `execution_adapter.is_paper is True` asserted at startup.
2. Config schema has **no** live/real-broker values.
3. No broker SDK import; no `ccxt` order-creation call anywhere.
4. Only one function constructs `Order`, after the risk gate.
5. Kill switch reachable and effective; never auto-clears.
6. Every order intent audited; audit hash-chain verifies.
7. Deterministic replay equality holds.
8. License CI gate green (no GPL/Commons-Clause in runtime).

Run `docs/19-claude-code-review-prompts.md` §19.1 (safety review) after every milestone and before any merge touching `risk/`, `execution/`, or `paper/`.

## 6. What NOT to build (guardrails)
Live broker/credentials · Sierra/DTC anything · cloud/multi-user/remote UI/auth · RL/LLM decision models · options/order-book/HFT · cross-sectional factor universes · portfolio-optimization layer (MVP sizing = fixed-fractional/vol-target) · React front end. Full list: `docs/16 §16.7`.

## 7. Open questions the product owner still needs to answer
None block Milestone 1. But before deep strategy work, resolve: real long-term market (crypto vs. futures), first exchange to standardize on, long/short vs long/flat, and single- vs multi-strategy MVP. See `docs/22-unanswered-questions.md`.

## 8. The one thing not to get wrong
The biggest failure mode is **not** the engine — it's **overfitting / look-ahead bias** making a broken strategy look brilliant, and quietly relaxing the kill-criteria when the honest protocol rejects most ideas. Treat `docs/09` as the product. Expect to kill most strategies; that's success.

## 9. Provenance
Every material claim in the specs is cited; the full source list is `docs/23-appendix-source-map.md`. Licenses/pricing were verified July 2026 and **drift** — re-verify anything cost- or license-sensitive before spending money or distributing.
