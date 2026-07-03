# 29 — Meta-Learning ("Super Model") System Spec

You asked for an ML system that watches all the models, learns which performs best under what conditions, keeps re-learning, and works toward a "super model." This is a legitimate and well-established idea — but the honest version is narrower and safer than the phrase suggests, and it **collides with two constraints you set earlier** (no autonomous LLM decisions; deterministic, testable strategies). This spec reconciles them.

## 29.1 What this actually is (naming it honestly)
The real technique is **meta-labeling** (Marcos López de Prado, 2017): a *secondary* ML layer that watches the *primary* models' signals and learns **how much to trust / how to size each one** — it does not invent its own trades. It separates the **side** (direction — owned by the base models) from the **size/confidence** (owned by the meta-layer), filtering false positives and scaling conviction. ([Meta-Labeling — Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling), [overview](https://whatworksintrading.substack.com/p/meta-labeling-the-technique-that)) Around it sit two supporting pieces: **regime characterization** (which conditions each model tends to do well/badly in) and **online drift monitoring** (has a model's behavior changed?).

So the "super model" = **a meta-labeling + regime-conditional weighting layer over the base models**, not a self-directed AI trader. That distinction is the entire safety story.

## 29.2 The honest truth you need before building it
- **Ensembling/meta-learning does not reliably manufacture profit.** It often overfits or degenerates into **performance-chasing** (piling into whatever model was recently hot, right before it reverts). In mixture-of-experts systems this shows up as **expert collapse** and routing instability. ([MoE failure modes](https://arxiv.org/pdf/2510.23027))
- **Financial data is hostile to naive ML:** non-stationary, low signal-to-noise, non-IID, reflexive. Standard ML tools fail when applied naively. ([López de Prado framing](https://whatworksintrading.substack.com/p/lessons-from-advances-in-financial))
- **A meta-layer multiplies overfitting risk**, because it's a model *of models* — more parameters, more trials, more ways to fool yourself. It therefore lives under **stricter** discipline than any base model (docs/09), not looser.
- **Value proposition (reframed):** the meta-layer's real payoff in this product is **analytical and educational** — it makes *legible* which models behave how under which conditions, as **testable hypotheses** you then validate. Treat "it found a super model" as a hypothesis to disprove, never a result to trade.

## 29.3 Safety policy (non-negotiable, reconciles with your earlier constraints)
1. **Observation-and-research only in the MVP.** The meta-layer **reads** the models' signals + outcomes and **produces analytics + suggested weights**. It does **not** place or size real (even paper) orders autonomously until a specific version has passed Research graduation (docs/09 §9.8) and a human enables it.
2. **When it is allowed to act (post-graduation), it acts deterministically.** Inference uses a **frozen, versioned** fitted model; given the same inputs it produces the same weights. "Keeps learning" happens as **periodic, offline, versioned retraining** — never live self-modification inside the decision loop. Every version is logged with its training data + metrics.
3. **It still goes through the risk gate.** Any meta-weight it suggests becomes a `SignalEvent`/sizing input that passes `make_order` + `StandardRiskEngine` like everything else. It cannot bypass a single safety control.
4. **No LLM in the decision path** (your constraint #3 holds). See §29.6 for the LLM's *only* allowed role.
5. **Auditable + reproducible:** every meta-decision (weights, features, model version) is written to the hash-chained audit log; replaying the recorded feed reproduces it.

## 29.4 Architecture (three quiet subsystems over the Floor)

```
   base models (10+) ──signals + fills──▶  [ Model Performance Ledger ]  (per-model, per-regime outcomes)
                                                    │
              live market/features ─▶ [ Regime Characterizer ]  (vol/trend/liquidity state, causal)
                                                    │
                                                    ▼
                                    [ Meta-Labeler / Weigher ]   ← the "super model"
                                    - input: base signal + regime + recent behavior
                                    - output: per-model CONVICTION (0..1) + suggested weight
                                    - offline-fit, frozen at inference, versioned
                                                    │
                        (MVP) analytics + Intelligence view  │  (post-graduation, human-enabled)
                        "who works when", correlations,      ▼
                         drift alerts, hypotheses      sizing input ▶ make_order ▶ risk gate ▶ PaperBroker
```

- **Model Performance Ledger:** records each base model's signals, fills, and outcomes tagged by regime — the training data for everything else. Built from the existing audit log.
- **Regime Characterizer:** labels the current market state **causally** (only data ≤ t): volatility (e.g. `arch`/EWMA), trend strength, liquidity, maybe HMM/`ruptures` regimes. Start with a *trivial* 2–3 state characterizer; add complexity only if ablation proves it helps (docs/03 §8).
- **Meta-Labeler / Weigher:** the core. A **gradient-boosted / logistic** meta-model (interpretable first — no deep nets) predicting each base model's **conviction** from {its signal, current regime, recent hit-rate/drift}. Emits conviction + a suggested weight. Offline-fit on purged/embargoed CV (docs/09), frozen at inference.
- **Drift monitor (the "keeps learning" done safely):** **online drift detection** (River's ADWIN/DDM/EDDM) watches each base model's live error stream and raises an alert when behavior shifts — triggering *review* and a *scheduled retrain*, not silent in-loop mutation. ([River](https://github.com/online-ml/river))

## 29.5 Libraries (all permissive; keep runtime clean)
- **scikit-learn** (BSD-3) — meta-model (logistic/RF/gradient boosting), CV.
- **LightGBM** (MIT) — gradient boosting for the weigher (interpretable importances).
- **River** (BSD-3) — online drift detection + optional incremental baselines. ([river](https://github.com/online-ml/river))
- **statsmodels / arch / hmmlearn / ruptures** — regime characterization (already in the plan, docs/02).
- All BSD/MIT → license gate stays green. Heavier ML libs go in the `research` extra, not the core runtime, unless/until a graduated meta-model is enabled.

## 29.6 The local LLM — honest verdict and its only safe role
**Feasibility:** yes — Ollama runs a 7–8B model (Llama 3.1 / Qwen 3 / Mistral) locally at Q4 on ~16GB RAM or an 8–12GB-VRAM GPU; 8GB RAM is the CPU-only floor. ([Ollama reqs 2026](https://localaimaster.com/blog/ollama-system-requirements)) So a local, private, $0 LLM is achievable.

**But it is the wrong tool for the core job, and here's the straight talk:** the "watch models and find patterns in their performance" task is **numerical pattern recognition over time series** — that's classical ML (LightGBM/River/HMM), not an LLM. LLMs are non-deterministic, weak at precise numerical reasoning, and would violate your own "no autonomous LLM decisions / deterministic strategies" constraints if placed in the loop.

**Its only allowed role = the Narrator/Analyst (never a decision-maker):**
- Turn the classical ML's structured output into **plain-English explanations** in the Intelligence view: *"Over the last N bars, the breakout model's conviction fell as volatility dropped; the mean-reversion model's rose. Historically this pairing has [survived / failed] out-of-sample — send to Research to check."*
- Help **draft hypotheses** and label regimes in words.
- **Hard constraints:** runs locally (Ollama), reads only already-computed structured analytics, **emits only text to the UI**, never a trade/size/order, never reads credentials (there are none), and its output is clearly tagged as commentary. It sits in the violet **Intelligence** channel, visibly separated from any number that could be mistaken for a decision.

If you never want an LLM, the system loses nothing functional — the narration just becomes templated text. The LLM is a *nice explainer*, not the brain.

## 29.7 Validation discipline (stricter than base models)
- Every meta-model version passes **purged & embargoed CV** and the docs/09 graduation gates, with **trial counting** across every meta-feature/hyperparameter tried → **Deflated Sharpe / PBO** on the *meta*-strategy, not just the base models. A meta-layer that "improves" in-sample almost always does; prove it out-of-sample.
- **Benchmarks the meta-layer must beat** to earn its keep: (a) equal-weight of the base models, (b) the single best base model, (c) a random weighting — at equal turnover, after costs. If it can't beat equal-weight out-of-sample, **it's noise; ship equal-weight.**
- **Ablate** the regime characterizer and each meta-feature; keep only what demonstrably helps.
- **Kill criteria** (docs/09 §9.9) apply to the meta-model *and* add: performance-chasing signature (weights just track trailing returns), instability across retrains, conviction that doesn't generalize.

## 29.8 How it shows up in the UI (Intelligence view, violet channel)
- **"Who works when" matrix:** models × regimes, cell = historical conviction/outcome (with sample sizes; low-n cells greyed as "insufficient").
- **Correlation web:** the Floor's violet threads — which models move together (diversification insight, not a P&L claim).
- **Drift alerts:** a quiet violet flag on any model whose behavior shifted (River detector fired) → "review / retrain."
- **Narration panel:** the LLM/templated plain-English read-out.
- **Every panel carries the honesty layer** (docs/26 §26.4): sample sizes shown, "simulated — not evidence of edge," and a one-click **Send to Research**. The Intelligence view is the most seductive screen after the leaderboard — it must be the most disciplined.

## 29.9 Acceptance criteria
- Meta-layer is **observation/research-only** by default; enabling it to influence sizing requires a graduated, versioned model + explicit human toggle, and still routes through the risk gate.
- Inference is deterministic + versioned; retraining is offline, scheduled, logged; drift detection raises reviews, not silent changes.
- The meta-strategy is evaluated against equal-weight/best-single/random benchmarks with DSR/PBO on honest trial counts; it ships only if it beats them out-of-sample after costs.
- LLM (if used) is local, text-only, in the Intelligence channel, never in the decision path; the "no LLM decisions" safety test still passes.
- Everything auditable + reproducible; runtime license gate stays green.

## 29.10 Build order (staged; part of Phase 3)
1. **Model Performance Ledger** (from the audit log) + the "who works when" matrix in the Intelligence view (pure analytics — highest value, lowest risk).
2. **Regime Characterizer** (trivial first) + drift monitor (River) → alerts.
3. **Meta-Labeler** (offline, interpretable) → conviction + suggested weights, **shown only** (not acting).
4. **Local LLM narrator** (optional) — templated fallback if absent.
5. **(Gated, later)** allow a *graduated* meta-model to influence *sizing* through the risk gate — only after it beats equal-weight out-of-sample.

> **Bottom line:** build the "super model" as a *disciplined analyst that explains and characterizes your models*, not an autonomous AI trader. That is the version that is safe, deterministic, auditable, genuinely useful — and honest about the fact that beating equal-weight out-of-sample is hard and may not happen.
