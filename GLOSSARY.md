# GLOSSARY — Canonical Vocabulary

Use these exact terms in code, comments, UI, and docs. Consistent vocabulary keeps the agent (and you) on the same page and prevents concept drift.

- **Paper trading** — fully simulated trading; the `PaperBroker` fills orders; no real money, no real orders. The only trading mode in this project.
- **PaperBroker** — the sole `ExecutionAdapter` (`is_paper=True`). Owns the fill simulator, slippage, and commission models.
- **Tracked book** — the live paper portfolio you watch. Accepts **only** gate-validated (promoted) configs; de-risks on degradation; its equity curve is the honest one.
- **Sandbox** — the exploration space where the autopilot is aggressive: unvalidated experiments, trials, and parameter changes. Never conflated with the tracked book.
- **Promotion** — moving a config from sandbox → tracked book. Happens only via the `PromotionGate`.
- **PromotionGate** — the code gate that returns `GateResult` (PASS/FAIL + evidence). Nothing reaches the tracked book without a PASS. Only it/the `Validator` can set `validated`.
- **Validator** — runs the out-of-sample checks (walk-forward, DSR, PBO, cost survival, benchmark beats) that the gate uses.
- **Walk-forward** — validation by rolling re-fit on in-sample windows and evaluating on the following out-of-sample window; the headline performance is the stitched OOS.
- **DSR (Deflated Sharpe Ratio)** — Sharpe corrected for how many configs/trials were tried (multiple testing), sample length, and non-normality. Honest trial-counting feeds it.
- **PBO (Probability of Backtest Overfitting)** — probability the best in-sample config underperforms out-of-sample; high PBO → discard.
- **Trial-counting** — recording every Optuna trial and every model tried, across the whole catalog, so DSR/PBO reflect the true search size.
- **Orchestrator** — the control flow of the learn→adjust→learn loop (rule-based or LLM-driven).
- **Optuna** — the numerical hyperparameter searcher. Does the actual parameter optimization the LLM cannot.
- **Narrator (LLM)** — the optional local LLM. Proposes what to explore + explains, emitting only 5 structured tool-calls; never optimizes, sizes, or judges.
- **Meta-labeling** — the honest framing of the "super model": a secondary layer that sizes/filters base models' signals; it does not invent trades.
- **Drift monitor** — River-based detector on the live tracked book; flags degradation/flattening that triggers a re-validation cycle.
- **De-risk** — the response to degradation: reduce exposure / pause / retire a model on the tracked book. Never "change params to chase the curve."
- **Autopilot** — the toggle handing the loop to the LLM/orchestrator. Aggressive but paper-only, audited, and gate-bound. OFF = manual.
- **Replay / ReplayClock** — deterministic historical playback (backtests, trials, validation).
- **WallclockClock** — real-time clock for the live paper daemon reading live public crypto data.
- **make_session** — the single function that builds the loop for both backtest and live (the parity guarantee).
- **make_order** — the single function that constructs an `Order`, after a non-REJECT risk decision. The only such path.
- **Kill / freeze** — the persistent, human-owned stop switch. Halts autonomy; the LLM cannot disable it; only a human clears it.
- **Audit log** — append-only, hash-chained JSONL of every event and autonomy action; source of truth; enables deterministic replay.
- **Honesty layer** — the mandatory overlays (sample sizes, "simulated — not evidence of edge", unproven vs validated, sandbox vs tracked) on every live/intel surface.
- **Unproven / validated** — a model's status. `validated` is set only by a gate PASS; everything else is `unproven` and cannot be ranked as validated.
- **StateReader** — the read-only interface the UI and 3D view use to get state/graph/tape. UI/3D never write except whitelisted control commands.
- **GraphPayload** — the node/edge/region structure the 3D neural-web renders (`docs/11` §11.9).
- **Manifest** — a model's metadata (family, rationale, data needs, params schema, failure modes, status) rendered by the catalog.
