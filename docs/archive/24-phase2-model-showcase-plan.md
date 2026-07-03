# 24 — Phase 2: Model Showcase Plan

**Why this file exists.** The MVP (docs 00–23, Milestones 1–10) was built as a *research bench*. The product owner's actual intent was different and clearer once seen against the build: **a catalog of credible ("institutional-grade") quant models, and a live view where you watch them trade real-time data in simulation.** This file recalibrates the product toward that intent — as an **additive Phase 2 on top of the existing engine**, not a rewrite.

> **Nothing about the safety model changes.** Every model in the showcase routes through the existing risk gate, audit log, kill switch, and paper-only lockout. Live trading remains structurally impossible. See docs/10, docs/11, docs/14, and §24.6 below.

## 24.1 What the owner asked for (confirmed)
- **Two equal modes:** a **Showcase** (browse models, watch them run live) and the existing **Research** bench — co-equal, switchable.
- **Full model catalog** across four families: (1) trend/momentum/breakout, (2) mean-reversion/pairs, (3) volatility-targeting/risk-parity/HRP, (4) factor/multi-asset.
- **"Many models racing" live view:** several models trading the same live feed side by side, compared in real time (a live leaderboard).
- **"Institutional-grade":** the model *families* institutions actually use (implemented from credible OSS libs) — **not** proprietary or pre-profitable black boxes. See §24.7.

## 24.2 What already exists and is reused (you did not waste the build)
- **Live paper daemon on real-time crypto data with simulated fills** (M8) — this *is* "watch a model trade live." The leaderboard runs N of these on one feed.
- **Strategy / Model plugin interfaces** (docs/12) — the catalog plugs straight in.
- **Risk gate, kill switch, hash-chained audit, reconciliation, deterministic replay** — every showcased model inherits these unchanged.
- **NiceGUI localhost UI** — extended into the two-mode shell.
- **Research analytics** (DSR/PBO/cost-sweep/ablation, M4) — becomes the Research mode and the leaderboard's honesty backbone.

**Net:** Phase 2 is a catalog + a live-comparison view + a mode shell on top of a finished engine.

## 24.3 The one hard truth this design must survive
A **live leaderboard is the most seductive surface in the whole product.** Watching a model "win" over hours or days is a tiny, cost-free, single-regime sample — exactly how sharp people talk themselves into trading a curve-fit. So the leaderboard is engineered to *inform, not seduce*: sample-size gating, costs applied live, "not significant yet" states, and a permanent "simulated — live performance is not edge" banner. Full rules: docs/26 §26.4. If a design choice makes the leaderboard more exciting but less honest, **honesty wins.**

## 24.4 Information architecture — two equal modes

```
┌───────────────────────────────────────────────────────────────┐
│ header:  lightweight-quant-engine   [ Showcase | Research ]     │
│          Mode: PAPER · Live trading: LOCKED   (always, red)     │
├───────────────────────────────────────────────────────────────┤
│ SHOWCASE                          │ RESEARCH (existing bench)   │
│ • Catalog gallery (cards by       │ • Backtest form + log       │
│   family; each shows what it is,  │ • Experiments table         │
│   rationale, data needs, risks)   │ • Equity/drawdown, blotter  │
│ • "Race" = live leaderboard:      │ • Cost sweep, ablation      │
│   pick models → watch them trade  │ • DSR / PBO, kill-criteria  │
│   the live feed side by side      │ • Tearsheet per run         │
│ • Drill-in: single-model live     │                             │
│   cockpit                         │                             │
│                                   │                             │
│ THE BRIDGE (both directions):     │                             │
│  Showcase "▶ Send to Research"  → validate honestly              │
│  Research "★ Add to Showcase"   ← only after it survives         │
└───────────────────────────────────────────────────────────────┘
```

**The bridge is the point.** Showcase creates curiosity ("that one looked interesting live"); Research is where curiosity is tested honestly ("does it survive costs / walk-forward / DSR?"). A model earns a *validated* badge in Showcase **only** after passing the docs/09 graduation criteria in Research. Un-validated models are clearly marked "unproven — for observation only."

## 24.5 Wave sequencing (my recommendation — you can override)
You selected all four families; building them all at once sprawls and front-loads the riskiest models. Staged instead:

- **Wave A (first, highest value):** two-mode shell + **directional catalog** (trend, momentum, breakout, single-asset mean-reversion) + **live leaderboard MVP** with honesty overlays. Single-asset, OHLCV-only, easiest to validate — you get the "watch models race live" experience fast and safely.
- **Wave B:** **portfolio-level models** (volatility targeting, risk parity, hierarchical risk parity) via skfolio/riskfolio. Requires multi-asset *basket* accounting.
- **Wave C:** **pairs/stat-arb** and **factor/multi-asset**. Requires multi-instrument data plumbing + careful statistics; highest overfitting/data risk. These may appear in Showcase for observation but are **gated behind Research validation** before they can be "ranked."

Rationale traces to docs/03 (trend/mean-reversion/momentum = MVP; pairs/portfolio-opt/factor = Later). The waves respect that risk ordering while still delivering your full vision.

## 24.6 Safety invariants carried forward (unchanged, must stay green)
1. Paper-only; `LIVE_TRADING_ENABLED=False`; only `PaperBroker`; config rejects live.
2. Every model's every order intent passes `StandardRiskEngine.check()` via the single `make_order` choke point — **the leaderboard does not create a new order path.**
3. UI constructs no `Order`, imports no risk/execution internals (extend the existing safety test to the new views).
4. Every event hash-chained + audited; deterministic replay reproduces the leaderboard.
5. localhost only; no new ports/hosts; no auth; no credentials.
6. Runtime deps stay MIT/BSD/Apache-2.0/NCSA; new libs (skfolio BSD-3, riskfolio BSD-3, statsmodels BSD-3, arch NCSA) pass the license gate.
7. No profitability claims anywhere; the "simulated — not edge" honesty layer is mandatory on every live view (new: `tests/honesty/`).

## 24.7 "Institutional-grade" — the labeling standard
Every catalog entry must display, on its card: **family**, **one-line economic rationale** (why the edge could exist), **data it needs**, **known failure modes** (from docs/03), and **validation status** (unproven / in-research / validated). This is what makes a model "institutional-grade" here: it's *named, understood, and honestly caveated* — never a black box. What we do **not** and **cannot** ship: a proprietary, pre-profitable model. The families are real; a downloadable guaranteed edge is not.

## 24.8 Acceptance criteria for Phase 2
- Two switchable modes; the bridge works both ways; validated badge only after docs/09 graduation.
- Catalog renders all built models with the §24.7 labeling; each model is a plugin behind the existing interfaces.
- Live leaderboard runs ≥3 models on one live feed concurrently, all through the risk gate + audit; replay reproduces it; honesty overlays present and tested (`tests/honesty/`).
- All existing safety tests still green; new safety/honesty tests added.
- No new runtime license violations; no new order path; no profit framing.

## 24.9 Files in this Phase-2 package
- **docs/25** — the model catalog spec (all four families, each mapped to the plugin interface).
- **docs/26** — the live leaderboard ("many models racing") spec + the anti-seduction honesty layer.
- **docs/27** — Claude Code milestone prompts for the developer, staged by wave.

> **Design ethos unchanged:** small, local, honest, one person can understand it. The showcase makes the models *visible and legible*; Research keeps you *from fooling yourself*. Both are needed — that's why they're co-equal.
