# 00 — Vision & Objective (FINAL, fresh handoff)

**Project:** `lightweight-quant-engine`
**Date:** 2026-07-03 · This is the fresh, authoritative handoff. Prior phased docs are preserved in [`archive/`](archive/) for deep-dive reference only — **build from this set.**

> **Disclaimer.** Research, engineering, and simulation infrastructure. No strategy or system here is claimed to be profitable. Nothing is financial advice.

## The product in one breath
A **local desktop-class app** (engine runs locally; GUI opens in a web browser on `localhost`) that hosts a large library of quantitative + statistical models, runs many of them **live on real-time market data in a paper (simulated) environment**, and puts an **autonomous LLM + ML "engine room"** behind them that continuously explores, tests, and adapts the models — with an **autopilot** you can switch on to ride as a passenger, and a **3D "neural-web" visualization** of the whole thing working. It costs ~$0/month to run and **cannot place a real trade.**

## What changed in this final version (vs. the archived plan)
1. **Packaging:** not a native Windows binary — the engine runs locally and the GUI is served on `localhost` in a browser. (Optional desktop window later.)
2. **Autonomy:** the LLM is promoted from "narrator" to **autonomous orchestrator** of a learn → adjust → learn loop, with an **aggressive autopilot** (see [`02`](02-autonomy-autopilot-and-learning-loop.md)).
3. **Scale:** the catalog expands toward "as many models as feasible," advanced statistical + proven quant ([`03`](03-model-catalog.md)).
4. **Visualization:** a dedicated animated **3D neural-web** space to watch it work ([`05`](05-ui-and-3d-visualization.md)).

## The objective — stated honestly
The owner's aim: *learn → adjust → learn, keep the equity curve rising with minimal drawdown.* The honest, buildable form of that objective:

> **Explore aggressively; promote only what survives out-of-sample; protect the tracked book when it degrades.**

Two surfaces make this work (this distinction is the spine of the whole system):
- **Sandbox** — where the autopilot is *aggressive*: the LLM+HPO loop tunes parameters, swaps models, runs scenarios freely on historical/held-out data and a shadow feed. Everything here is explicitly **unvalidated**.
- **Tracked (promoted) book** — the equity curve you actually watch. It **only accepts changes that passed out-of-sample validation** (walk-forward, deflated Sharpe, PBO — [`04`](04-validation-and-overfitting-protocol.md)). On degradation it **de-risks and re-validates**; it never chases the curve.

**Why "keep the curve going up and up" cannot be the raw objective** [Certain]: a loop that changes parameters to make *recent* performance rise will fit to noise — a rising curve is the *symptom* of that overfit, not proof of skill (Bailey & López de Prado). Aggressive exploration is free and encouraged; **promotion is disciplined**. That combination is a system that genuinely learns instead of one that fools itself.

## Non-negotiables (the whole set, final)
1. **Paper-only. No real orders, no broker credentials, ever, in this product.** This is the one rail that stops financial harm — it stays hard.
2. **Full audit + determinism of execution.** Every LLM/ML action and every event is logged to a hash-chained audit; a given config replays bit-for-bit. Without this the learning loop and the 3D view are unreproducible noise. (Not a "safety" rule — a *make-it-real* rule.)
3. **Promotion gate.** No parameter change reaches the tracked book until it passes out-of-sample validation. The LLM explores freely; the math decides what's real.
4. **The GUI shows no CLI/stdout** — structured, designed components only ([`05`](05-ui-and-3d-visualization.md)).
5. **Local-first, single-user, `localhost` only.** Nothing exposed to a network; no auth needed because nothing is reachable.
6. **Deterministic model *execution*.** Models/strategies are deterministic given params+data+seed; the LLM chooses *what* to run, never injects nondeterminism into a sim result.
7. **No profitability claims** anywhere in code, UI, or docs.

## What it is / is not
| It IS | It is NOT |
|---|---|
| An autonomous research + paper-trading **simulator** | A live brokerage / real-money system |
| An LLM+ML **engine room** that explores and adapts | A guaranteed profit machine |
| Honest: aggressive in the sandbox, validated on the tracked book | A loop that chases the recent equity curve |
| A large, extensible model catalog | A pile of unvalidated models mistaken for robustness |
| A cinematic 3D view of real system state | A fake "AI brain" that implies more than it knows |

## Reading order
[`01`](01-system-architecture.md) architecture → [`02`](02-autonomy-autopilot-and-learning-loop.md) the autonomy/autopilot loop → [`04`](04-validation-and-overfitting-protocol.md) the validation discipline (the real product) → [`05`](05-ui-and-3d-visualization.md) UI + 3D → [`08`](08-build-plan-and-claude-code-prompts.md) build plan/prompts. Challenge it with [`09`](09-decision-log-risks-open-questions.md).
