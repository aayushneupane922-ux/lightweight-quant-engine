# 02 — Autonomy, Autopilot & the Learning Loop (FINAL)

The engine room: an autonomous LLM+ML system that explores and adapts the models in a continuous **learn → adjust → learn** loop, with an **aggressive autopilot** you can ride. Grounded in 2026 LLM-HPO research: LLM agents orchestrate hyperparameter search well, but classical optimizers (Optuna) + rigorous validation do the actual judging. ([AgentHPO](https://arxiv.org/abs/2402.01881), [OptiMindTune multi-agent HPO](https://arxiv.org/html/2505.19205v2), [AutoResearch vs classical HPO](https://www.weco.ai/blog/autoresearch-vs-classical-hpo))

## 2.1 Division of labor (LLM and ML are complementary)
| Role | Who | Does |
|---|---|---|
| **Curiosity / strategy** | **LLM** | decides *what* to explore: which models, which params, which scenarios, what hypothesis; interprets results; narrates in plain English |
| **Search / optimization** | **Optuna (HPO)** | the actual numerical parameter search over the space the LLM proposes (TPE/CMA-ES); seeded, reproducible |
| **Judgment / promotion** | **Validator + PromotionGate** | walk-forward + deflated Sharpe + PBO decide if a candidate is real ([`04`](04-validation-and-overfitting-protocol.md)) |
| **Drift watch** | **River** | monitors live-book behavior; raises "degrading/flattening" flags |
| **Explanation** | **LLM (narrator)** | turns all of the above into the Intelligence narration + 3D view labels |

The LLM never does the numerical optimization itself (it's bad at it and non-deterministic) and never overrides the Validator. It's the **orchestrator and explainer**; the math is the **judge**.

## 2.2 The learn → adjust → learn loop
```
        ┌───────────────────────────────────────────────────────────────┐
        ▼                                                               │
 (1) OBSERVE   live tracked book + sandbox: performance, drift, regime  │
        │                                                               │
 (2) HYPOTHESIZE  LLM: "vol is rising; breakout params look stale;      │
        │          try wider Donchian + tighter stops in this regime"   │
        ▼                                                               │
 (3) SEARCH    Optuna runs seeded trials over the proposed space,       │
        │       each trial = a walk-forward backtest on held-out data   │
        ▼                                                               │
 (4) VALIDATE  best candidate → out-of-sample gate (WF, DSR, PBO,       │
        │       beats equal-weight/best-single/random after costs)      │
        ▼                                                               │
 (5) DECIDE    PASS → promote to tracked book (audited).                │
        │       FAIL → log hypothesis as killed, LLM learns, loop.      │
        ▼                                                               │
 (6) NARRATE   LLM explains what happened; 3D view updates. ───────────┘
```
- **Aggressive in steps 1–3** (sandbox): the LLM can spin up many hypotheses/trials fast, swap models, reshape spaces — no limits beyond compute.
- **Disciplined at steps 4–5** (tracked book): nothing is promoted without passing the gate. This is what keeps the watched equity curve honest.

## 2.3 The autopilot
A single, prominent **Autopilot** toggle (final spec = **aggressive**):

- **ON:** the LLM autonomously runs the full loop *and* manages the tracked paper book — proposing, searching, validating, promoting, reallocating, and de-risking on degradation — at high tempo. You **ride and observe** (the 3D view + Obsidian Desk narrate everything in real time). It can tune models, risk parameters, allocations, and the sandbox freely.
- **OFF:** you drive — change any parameter, launch scenarios, promote/reject candidates yourself. The LLM becomes advisory (suggests + explains).
- **Take-the-wheel:** flipping OFF at any moment freezes autonomous changes immediately; the current tracked config keeps running until you change it.
- **Kill / freeze:** a persistent, human-owned control that halts all autonomous activity and (optionally) flattens the sim book. It's *your* stop button — always available, survives restart.

Because everything is **simulated**, the autopilot's authority is broad by design; the only hard limit is that it operates on a **paper book** and every action is **audited**.

## 2.4 Degradation response (your "threshold" idea, done right)
You asked: if performance degrades or flattens, immediately change parameters. The honest mechanism:
- **Detect** (River drift + threshold): the tracked book's risk-adjusted performance drops below a set floor, or flattens (no improvement over a window), or drawdown breaches a limit.
- **Protect first:** the tracked book **de-risks** (cuts exposure / pauses the weak model) — capital-preservation before cleverness.
- **Re-validate, don't chase:** the degradation *triggers a fresh search+validation cycle* in the sandbox. A replacement config reaches the tracked book **only if it passes the gate.**
- Why not "immediately change live params"? Because changing the live book to fix a recent dip *is* the overfitting failure — it optimizes for the last data point. De-risk-then-revalidate gets you adaptivity without self-deception. (You chose this; it's the right call.)

## 2.5 The LLM's authority — scope & boundaries (sim)
**Can (autopilot on):** propose/prioritize hypotheses; define/adjust search spaces; launch Optuna runs, scenarios, backtests; read all metrics/audit; tune sandbox models + risk params; promote *validated* candidates; de-risk/pause tracked models; reallocate the sim book; write narration.
**Cannot (structural):** place a real order, hold a credential, reach a broker (paper-only lockout); bypass the audit log; mark a candidate "validated" without the Validator's pass; disable the human kill switch; inject nondeterminism into a sim result (its actions are logged so runs replay).

These aren't safety-against-money limits (it's a sim) — they're the **integrity** limits that make the system reproducible and honest.

## 2.6 Local LLM (optional) — role & reproducibility
- **Model:** a local Ollama model (Llama 3.1 8B / Qwen 3 8B, Q4) — see [`07`](07-cost-stack-and-local-llm.md). Runs on ~16GB RAM; $0.
- **Role:** the orchestrator's reasoning + narration. It reads structured state (metrics, drift, regime, catalog), emits **structured tool calls** (propose_space, run_trials, promote_if_valid, de_risk, narrate) — never freeform trades.
- **Determinism of record:** log prompt + response + model + seed/temperature for every call; the *decision* is captured even though the model is stochastic. Set low temperature for the control loop.
- **Fallback:** if no LLM is present, a **rule-based orchestrator** runs the same loop (Optuna + validation + drift) with templated narration — the system loses cleverness of hypotheses, not function.

## 2.7 "Use as many models as possible" — handled honestly
Breadth is welcome and supported ([`03`](03-model-catalog.md)) — but [Certain] **more models ≠ more robust.** Testing more models/spaces on the same data inflates the best one's apparent edge (multiple testing). So the loop **counts every trial and every model tried** and feeds that count into the deflated-Sharpe/PBO gate ([`04`](04-validation-and-overfitting-protocol.md)). A giant catalog is a bigger overfitting surface; the promotion gate is what makes size safe rather than dangerous.

## 2.8 Acceptance criteria
- The loop runs autonomously end-to-end (observe→hypothesize→search→validate→decide→narrate); every step audited + replayable.
- Autopilot ON = aggressive autonomous management of the sandbox + tracked book; OFF = manual; kill/freeze always works and is human-owned.
- No candidate reaches the tracked book without passing the Validator; degradation de-risks then re-validates (never chases).
- Optuna search is seeded/reproducible; LLM actions are logged; runs replay from the log.
- Works with the LLM absent (rule-based fallback). Paper-only lockout intact.
