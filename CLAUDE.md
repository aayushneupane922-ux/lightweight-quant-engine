# CLAUDE.md — Agent Constitution

> Loaded every session. Keep this file lean. Detail lives in the three operating files below and in `docs/`. When unsure, **stop and re-read `GUARDRAILS.md`**, then pick the smaller, safer, more deterministic, more honest option.

## Operating files (read these; they keep you on-rails)
- **`GUARDRAILS.md`** — the boundary fence: what you must NEVER do, what is OUT OF SCOPE, and exactly when to STOP and ask the human. Read before adding anything new.
- **`WORKFLOW.md`** — the per-change loop, definition of done, review gates, commit/tag discipline. Follow it every change.
- **`GLOSSARY.md`** — canonical vocabulary. Use these exact terms; don't invent new ones.
- **`docs/00`–`11`** — the specs. `docs/10` = build order (milestones + gates). `docs/11` = implementation contracts. `docs/archive/` = superseded; **do not build from it.**

## What this is
A LOCAL, PAPER-ONLY, autonomous quant research **simulator**. Engine runs locally; GUI on `127.0.0.1` in a browser. An LLM+ML "engine room" runs a learn→adjust→learn loop over a large model catalog, with an aggressive **autopilot** and a **3D neural-web** view. Built for honest research and a great "watch it work" experience — never for claimed profit. **No product code exists yet; first code = Milestone 1 (`docs/10`).**

## The 9 non-negotiables (never violate — full detail in GUARDRAILS.md)
1. Paper-only. No real orders, no broker SDK, no credentials. `PaperBroker` is the only `ExecutionAdapter` (`is_paper=True`, asserted at startup). `LIVE_TRADING_ENABLED=False`, no flip; config rejects live.
2. Full audit + determinism: every event AND autonomy action is hash-chain logged; execution is deterministic per config+seed; sessions replay from the log.
3. Promotion gate: nothing reaches the TRACKED book without passing out-of-sample validation (walk-forward + DSR + PBO + cost + beats equal-weight/random). Only the `Validator` sets `validated`.
4. Two surfaces: SANDBOX (aggressive, unvalidated) vs TRACKED book (validated only; de-risks on degradation; never chases the curve). Never conflate them.
5. LLM ORCHESTRATES + narrates; **Optuna** searches; **Validator** judges. The LLM never optimizes numerically and never overrides the gate. Its actions are logged.
6. Human KILL/freeze is un-overridable by the LLM. Autopilot is aggressive but paper-only + audited.
7. GUI renders NO CLI/stdout — structured components only. `localhost` only; no auth; no network exposure.
8. Runtime deps MIT/BSD/Apache/NCSA only (license CI gate). Models deterministic + manifest-complete or quarantined.
9. No profitability claims. "Equity up" = the tracked, gate-passed, out-of-sample, after-cost book only.

## The loop invariant (memorize)
The **system** learns (Optuna search + walk-forward validation on historical/held-out data); the **LLM steers and explains**; validated configs **run live on real-time paper data**; live drift **triggers** re-learning back on history; **nothing untested touches the live book.**

## Architecture in one line
Own the spine (event loop, clock, order state machine, accounting, risk model, audit, paper broker, orchestrator control flow); rent the muscles behind interfaces (ccxt, DuckDB/Polars, pandas-ta/statsmodels/arch/skfolio/…, sklearn/LightGBM/River/Optuna, Ollama, three.js/3d-force-graph). Contracts: `docs/11`.

## Definition of done (every change)
ruff+mypy clean · all tests green (unit + property + parity + safety + honesty) · audit hash-chain verifies · PromotionGate un-bypassable · GUI has no CLI/stdout · sandbox≠tracked · license gate green · docs updated. See `WORKFLOW.md`.

## First action
Read `docs/00,01,02,04,06,10,11` + `GUARDRAILS.md` + `WORKFLOW.md`. Then implement **Milestone 1** (`docs/10`): deterministic core + paper-only lockout + audit, with tests. **STOP for review.** Build **M4 (the gate) before M8 (autonomy)** — never run the learner without the judge.
