# 31 — Phase 3 Milestone Prompts (UI System · Meta-Learning · Catalog Scale)

Run **one at a time**, after `CLAUDE.md` + docs/24–30, and after Phase 2 (docs/27) is green. Phase 3 is still **additive** — it never weakens a safety invariant; it extends the UI, adds the meta-learning *analytics*, and scales the catalog. Every prompt ends with "STOP for review" (docs/19 §19.1 safety + the honesty checklist).

**Pre-flight:** base build green (`pytest -q`, `ruff`, `mypy src`, `license_gate.py`); Phase 2 leaderboard + honesty suite green.

---

## Q1 — Reskin to "Obsidian Desk" + kill the CLI feed  [UI]
```
Apply the docs/28 design system to the NiceGUI app as a THEME LAYER (CSS custom-property
tokens + a small component library / Quasar overrides + ECharts dark theme). Ship Inter +
JetBrains Mono (free, OFL) as the default faces; all numbers use the mono face with
tabular-nums. Build the "desk" layout: status rail (feed health, UTC clock, PAPER·LIVE LOCKED
amber shield, session sim-P/L, KILL), left mode spine (Floor/Catalog/Research/Intelligence/
Risk with function-key + ⌘K nav), center hero, right inspector, optional bottom Tape drawer.
REMOVE the CLI/log terminal entirely: replace with a progress strip, structured tables/KPIs/
charts, and a designed Tape (one row per audit event) — the GUI must render NO raw stdout.
Tests: a UI test asserts no element renders unstructured stdout/CLI text; visible focus rings;
prefers-reduced-motion respected; still 127.0.0.1 only; existing safety/honesty suites green.
Acceptance: the app looks like docs/28 (match the mockup) and contains no CLI feed. STOP for review.
```

## Q2 — Model Floor + instrument cells  [UI · hero]
```
Build the Model Floor (docs/28 §28.6): a live grid of model instrument cells. Each cell:
family glyph + name, state badge (ARMED/FIRED/LONG/SHORT/HALTED), stance bar (long right /
short left), mono micro-readouts (sim-return caveated, #trades), a 24-bar sparkline, and a
left-edge --intel tint for meta-conviction (wired in Q5; static for now). Fire pulse on trigger
(reduced-motion safe). The Floor renders the Phase-2 live race (docs/26) in this new form; the
honesty layer (sample size >= P&L weight, 'insufficient data', 'simulated — not edge') is
preserved. Drill-in opens the inspector cockpit for one model.
Tests: cells reflect audit state; honesty overlays present; no Order constructed in UI.
Acceptance: 10+ models visibly armed/firing on one live feed in the Obsidian Desk floor. STOP for review.
```

## Q3 — Catalog scale (adapters + intake)  [Catalog]
```
Implement docs/30: the plugin contract + library-adapter pattern. Build adapters that unlock
families via config — PandasTaRuleAdapter (indicator+rule presets), SkfolioOptimizerAdapter,
PyPortfolioOptAdapter, RiskfolioAdapter — plus the intake checklist (license/deterministic/
manifest/tests/status=unproven) and a transparent quarantine list. List >=10 concrete models
across the four families for a real racing floor; ensure the architecture scales to 50+ without
per-model bloat. Heavy libs (skfolio/riskfolio/lightgbm) go in the `research` extra; keep the
runtime license gate green.
Tests: adding a model = folder passing intake; adapters produce deterministic strategies;
license gate green; catalog browse/filter/search works.
Acceptance: >=10 models listed and race-able; adapters unlock families by config. STOP for review.
```

## Q4 — Intelligence analytics (Model Performance Ledger + regime + drift)  [ML · read-only]
```
Implement docs/29 §29.4 steps 1-2 as PURE ANALYTICS (no acting): the Model Performance Ledger
(from the audit log: per-model signals/fills/outcomes tagged by regime), a trivial Regime
Characterizer (causal vol/trend state; arch/EWMA), and an online Drift Monitor (River ADWIN/
DDM) raising review flags. Build the Intelligence view (docs/28/29): the "who works when"
models×regimes matrix (with sample sizes; low-n greyed), the Floor correlation web (--intel
violet), and drift alerts. Everything read-only, honesty layer mandatory.
Tests: ledger reconstructs from audit deterministically; regime labels are causal (no lookahead);
drift monitor fires on injected drift; matrix greys low-n cells; no Order path touched.
Acceptance: Intelligence view characterizes models honestly from real runs. STOP for review.
```

## Q5 — Meta-labeler (the "super model") — SHOWN, not acting  [ML · gated]
```
Implement docs/29 §29.4 step 3: an interpretable meta-labeler (LightGBM/logistic) that predicts
each base model's CONVICTION from {its signal, current regime, recent behavior}, offline-fit
with purged/embargoed CV (docs/09), FROZEN at inference, versioned. Output = per-model conviction
+ suggested weight, wired to the cell --intel tint and an Intelligence panel. It is OBSERVATION-
ONLY: it constructs no Order and influences no sizing yet. Evaluate the meta-strategy vs equal-
weight / best-single / random benchmarks with DSR/PBO on honest trial counts; surface the verdict.
Tests: inference deterministic + versioned; CV is purged/embargoed; meta-model cannot emit an
Order or a size (assert); benchmark comparison + DSR/PBO produced; safety suite green.
Acceptance: the meta-layer shows conviction + an honest 'does it beat equal-weight?' verdict,
and touches no order path. STOP for review.
```

## Q6 — Local LLM narrator (optional)  [ML · text-only]
```
Add an OPTIONAL local LLM narrator (docs/29 §29.6) via Ollama (Llama 3.1 8B / Qwen 3 8B, Q4).
It reads ONLY already-computed structured analytics and emits PLAIN-ENGLISH commentary into the
Intelligence view's violet channel. Hard constraints: local only, text-only, no trade/size/order,
no credentials, clearly tagged as commentary; if Ollama is absent, fall back to templated text
(no functional loss). The narrator is never in the decision path.
Tests: narrator emits only text; a safety test asserts no LLM output reaches sizing/orders; app
works with the LLM absent (templated fallback).
Acceptance: optional local narration explains what the ML found, safely. STOP for review.
```

## Q7 — (Gated, optional, LATER) let a graduated meta-model influence sizing  [ML · risk-gated]
```
ONLY after a specific meta-model VERSION passes Research graduation (docs/09 §9.8) AND beats
equal-weight out-of-sample after costs: allow it to influence SIZING (not direction) as a
deterministic, frozen input that becomes a SignalEvent/size passed through make_order +
StandardRiskEngine like any other. Add an explicit human enable toggle (default OFF), full audit
of every meta-weight, and a one-switch revert to equal-weight. Still paper-only; still no LLM in
the loop.
Tests: disabled by default; when enabled, every meta-weight audited and passes the risk gate;
revert works; determinism/replay hold; all safety + honesty suites green.
Acceptance: gated, auditable, reversible meta-sizing that cannot bypass a single control. STOP for review.
```

## Q8 — Phase-3 safety, honesty & design review
```
Consolidate: extend tests/safety (no Order from Floor/Intelligence/narrator; no LLM in decision
path; meta-model can't size unless graduated+enabled) and tests/honesty (Intelligence view
carries sample sizes + 'simulated — not edge'; no profit framing; validated-only badges). Verify
the GUI renders no CLI/stdout anywhere. Re-run docs/19 §19.1 + honesty checklist; license gate
green; determinism/replay/parity hold. Update HANDOFF.md/README with Phase-3 features + the new
Intelligence and design system.
Acceptance: all gates green with evidence; the terminal looks institution-grade (docs/28), hosts
a broad honest catalog, and the meta-layer is a disciplined analyst — not an autonomous trader.
STOP for review.
```

---

## Guardrails for the whole phase
- Additive only; never weaken a safety invariant; extend tests, don't relax them.
- The GUI renders **no CLI/stdout** — structured components only (docs/28 §28.8).
- The meta-layer is **observation/research-only** until graduated + human-enabled; it never bypasses the risk gate; no LLM in the decision path (your constraint #3).
- Color = meaning (docs/28 §28.2); honesty layer mandatory on every live/intelligence surface.
- Runtime stays permissive (heavy ML/LLM libs opt-in); localhost only; paper only; no profit claims.
- Build order Q1→Q8; after Q2 you already have the "future terminal watching 10 models live" you asked for.
