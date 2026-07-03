# 27 — Phase 2 Milestone Prompts (for Claude Code / the developer)

Run **one at a time**, after loading `CLAUDE.md` + docs/24–26. Each preserves every existing safety invariant and ends with "STOP for review" (run docs/19 §19.1 + the new honesty review after any UI/model/paper change). Phase 2 is **additive** — do not modify the engine's safety core except to *extend* tests.

**Pre-flight (do first):** confirm the current build is green on this machine — `pytest -q`, `ruff check .`, `mypy src`, `license_gate.py` — and that docs/19 §19.1 safety review passes with evidence. Do not start Phase 2 on a red base.

---

## P1 — Two-mode UI shell (Showcase | Research)  [Wave A]
```
Add a top-level mode switch to the NiceGUI app: [ Showcase | Research ]. Move the existing
control panel/results into RESEARCH (unchanged behavior). Create an empty SHOWCASE mode with
a catalog gallery placeholder and a "Race" placeholder. Keep the red "Mode: PAPER · Live
trading: LOCKED" banner global. No engine changes. The UI still imports no risk/execution
internals and constructs no Order.
Tests: existing tests/safety green; a UI test asserts both modes render and the mode switch
works; assert still bound to 127.0.0.1 only.
Acceptance: two switchable modes; Research works exactly as before; Showcase is a labeled shell.
STOP for review.
```

## P2 — Catalog framework + directional models  [Wave A]
```
Implement the model-catalog framework (docs/25): a manifest schema (pydantic) + plugin
discovery + Showcase cards rendering name/family/rationale/data-needs/failure-modes/status.
Implement these models as plugins behind the EXISTING Strategy interface (deterministic,
SignalEvent-only, no Order): trend_macd, breakout_donchian, momentum_tsmom, meanrev_zscore,
meanrev_bollinger, meanrev_rsi (trend_ma_cross already exists). Each ships a manifest + unit
tests + a Research validation run (backtest + cost sweep + DSR).
Wire the Showcase card buttons: "Send to Research" (opens Research bound to that model) and a
disabled "Add to Race" (enabled in P3). status starts 'unproven'; only a graduation run sets
'validated' (docs/09 §9.8) — authors cannot set it.
Tests: each model deterministic + replay-equal; manifest validates; safety suite green.
Acceptance: catalog gallery shows ≥6 models with full labeling; each runs in Research.
STOP for review.
```

## P3 — Live leaderboard ("many models racing")  [Wave A]
```
Implement the live leaderboard (docs/26). Run N (2..5) models concurrently on ONE shared live
public feed via the existing paper daemon / make_session (do NOT fork it; do NOT open N
exchange connections). Each model gets an isolated sub-account; ALL orders route through
make_order + StandardRiskEngine + audit. Add the leaderboard table + single-model drill-in
cockpit.
Implement the honesty layer (docs/26 §26.4) IN FULL and cover it with a new tests/honesty/
suite: persistent 'SIMULATED — not edge' banner; sample-size (elapsed/bars/trades) shown with
>= weight than P&L; 'insufficient data' state below min_trades_for_rank; costs shown, never
zero; rank_by is NOT raw P&L; verdict chips; per-row 'Send to Research'; validated badge only
for graduated models.
Kill hierarchy: global KILL stops all; per-model halt isolates one; both audited.
Tests: a recorded race replays deterministically to the same leaderboard; global kill + per-
model halt tested; tests/honesty enforces every §26.4 rule; tests/safety still green; UI
constructs no Order.
Acceptance: ≥3 models race live, honestly, isolated, replayable, killable. STOP for review.
```

## P4 — Portfolio models + basket accounting  [Wave B]
```
Add multi-asset BASKET support to the session (aligned bars across >=3 symbols; per-symbol
sub-accounting; shared risk gate). Implement portfolio models behind the Model interface:
vol_target (reuse EwmaVolModel pattern), risk_parity (riskfolio-lib), hrp (skfolio or
PyPortfolioOpt), and mvo (PyPortfolioOpt) as a DELIBERATELY cautionary baseline. Each converts
weights → SignalEvents → make_order (no Order in the model). Add skfolio/riskfolio/PyPortfolioOpt
to the RESEARCH extra (not runtime) if the license gate prefers; confirm all are BSD-3/permissive
and the gate stays green.
Tests: basket accounting reconciles; each optimizer deterministic; ablation shows whether it
helps; license gate green; safety green.
Acceptance: portfolio models run in Research and can enter a Race; mvo visibly flagged as an
unstable baseline. STOP for review.
```

## P5 — Pairs / stat-arb + factor / multi-asset  [Wave C]
```
Add multi-instrument plumbing: aligned dual-series for pairs; a ranked universe (survivorship-
safe, docs/08) for factor models. Implement pairs_coint (statsmodels cointegration) and
factor_xsec_momentum / factor_lowvol (own + pandas). These carry the HIGHEST overfitting risk:
enforce multiple-testing discipline — count every pair/factor combination tried and report DSR/
PBO accordingly (docs/09 §9.7). In Showcase these may be OBSERVED live but must be gated: they
cannot show a 'validated' badge or a ranked position until they pass a Research graduation run.
Tests: cointegration/ranking deterministic; multiple-testing count recorded; gating enforced
(unproven pairs/factor cannot be 'ranked/validated'); safety + honesty suites green.
Acceptance: pairs + factor models observable live, honestly gated, validated only via Research.
STOP for review.
```

## P6 — Phase-2 safety & honesty review  [after each wave, mandatory before "done"]
```
Consolidate and prove Phase-2 doesn't regress safety or honesty:
- Extend tests/safety to the new views: leaderboard/cockpit construct no Order, import no
  risk/execution internals, add no host/port; every model's orders pass make_order.
- tests/honesty fully covers docs/26 §26.4 (banner, sample-gating, cost display, non-P&L rank,
  no-profit-language lint, verdict chips, validated-only-after-graduation).
- Re-run docs/19 §19.1 (safety) + a new §honesty checklist; license gate green; determinism +
  replay-of-race parity hold.
- Update HANDOFF.md/README with the new modes and the Phase-2 status.
Acceptance: all gates green with evidence; no profit framing anywhere; live views cannot be
mistaken for a profitability claim. STOP for review.
```

---

## Guardrails for the whole phase (repeat to the agent)
- Additive only: never weaken the engine's safety core; extend tests, don't relax them.
- Every model is deterministic, SignalEvent-only, and passes through `make_order` + the risk gate.
- The leaderboard is honest by construction (docs/26 §26.4) or it doesn't ship.
- New runtime deps must be permissive (skfolio/riskfolio/statsmodels/arch are BSD-3/NCSA); prefer the `research` extra where possible; keep the license gate green.
- localhost only; paper only; no credentials; no profitability claims.
- Build in wave order (A→B→C); each wave is usable on its own — you get "watch models race live" at the end of Wave A.
