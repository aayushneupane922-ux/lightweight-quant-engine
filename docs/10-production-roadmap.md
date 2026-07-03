# 10 — Production Roadmap (Solo + Claude Code)

A step-by-step, production-ready build plan for one builder driving Claude Code. Granular task checklists, acceptance **exit gates**, dependencies, and S/M/L sizing — **no hard dates** (recalibrate to your own velocity). Pairs with the milestone prompts in [`08`](08-build-plan-and-claude-code-prompts.md) and the agent context in [`CLAUDE.md`](CLAUDE.md).

> "Production-ready" here = a robust, packaged, local application within the **paper-only** envelope. It does **not** mean live-trading-ready — that is out of scope by hard rail ([`06`](06-engine-data-risk-and-audit.md) §6.6).

## How to run this as a solo builder
1. **One milestone per focused session.** Don't start the next until the current **exit gate** is green.
2. **Tests-first where practical.** Ask Claude Code to write the safety/honesty/property tests with (or before) the implementation.
3. **Self-review at every gate** using [`archive/19-claude-code-review-prompts.md`](archive/19-claude-code-review-prompts.md) §19.1 (safety) + the honesty checklist. Absence of evidence = FAIL.
4. **Commit + tag at each gate** (`git tag mN-done`) so you can always roll back to a known-good state.
5. **Use Claude Code subagents** (below) to parallelize: one drafts tests, one implements, one reviews.
6. **Definition of Done (every commit):** ruff + mypy clean · all tests green (unit + property + parity + safety + honesty) · audit hash-chain verifies · PromotionGate un-bypassable · GUI renders no CLI/stdout · license gate green · docs touched. If any is red, stop and fix — never merge red.

**Sizing legend:** S = a session or two · M = several sessions · L = a multi-session mini-project. **Dep** = must be done first.

## Critical path (the spine — do these in order)
`M0 → M1 → M2 → M3 → M4 → M8` gives a **headless, honest, autonomous loop** (the hard core). Then layer **M5, M6, M7** (safety hardening, catalog, UI), then **M9, M10** (autopilot + 3D), then **M11, M12** (scale + hardening/release). Everything else hangs off this spine.

## Release checkpoints (thin-slice first)
- **v0.1 — Honest loop (headless):** M0–M4. You can ingest, backtest, and *validate* — the gate exists. Nothing autonomous yet. ✅ **shipped**, tag `v0.1` — `lqe ingest`/`lqe backtest`/`lqe validate` verified end-to-end on real BTC-USDT/ETH-USDT data.
- **v0.2 — Usable terminal:** + M5, M6, M7. Catalog + Obsidian Desk UI + risk/kill. ✅ **shippable** at `m7-done` — `lqe desk` serves the Floor/Catalog/Research/Risk/Daily views on 127.0.0.1, read-only over the audit log with a human KILL.
- **v0.3 — Autonomous:** + M8, M9. Learn→adjust→learn loop + aggressive autopilot + local LLM. ✅ **shippable** at `m9-done` — rule-based loop runs headless (`lqe autopilot`), the desk shows decision cards + an autopilot toggle, and an optional Ollama narrator plugs in (fail-closed, replay-logged).
- **v0.4 — Cinematic:** + M10. Interactive 3D neural-web + timeline replay. ✅ **shippable** at `m10-done` — the Engine view renders the live neural-web from the audit and scrubs the timeline for deterministic replay (canvas renderer; three.js vendor slot documented).
- **v1.0 — Production-ready local app:** + M11, M12. Scaled catalog, hardened, packaged installer.

---

## M0 — Environment & scaffold  · S · Dep: none  ✅ `m0-done`
- [x] Install Python 3.12+, git; create repo `lightweight-quant-engine`, `git init`.
- [x] Create venv; `pyproject.toml` with the fixed stack ([`07`](07-cost-stack-and-local-llm.md) §7.2); pin versions.
- [x] Scaffold `src/lqe/` package tree + `tests/{unit,property,parity,safety,honesty,integration}` ([`08`](08-build-plan-and-claude-code-prompts.md) §8.1).
- [x] Add `CLAUDE.md` (repo root) + `docs/` (this fresh set) + `docs/archive/`.
- [x] Configure `ruff`, `mypy --strict`, `pytest`, `pre-commit`; add `.gitignore` (ignore `data/`, `runs/`, `*.duckdb/parquet/jsonl`).
- [x] Add `.github/workflows/ci.yml`: ruff + mypy + pytest + `scripts/license_gate.py`.
- [x] `constants.py`: `LIVE_TRADING_ENABLED=False`.
- **Tests:** CI runs green on an empty skeleton; license gate passes.
- **Exit gate:** `pytest` + `ruff` + `mypy` + license gate all green on the empty scaffold; `git tag m0-done`.

## M1 — Deterministic core + paper-only lockout + audit  · M · Dep: M0  ✅ `m1-done`
- [x] `core/events.py`: immutable pydantic events + autonomy events ([`06`](06-engine-data-risk-and-audit.md) §6.2), hash-chain envelope.
- [x] `core/clock.py`: `Clock` protocol + `ReplayClock` + `WallclockClock` (time always injected).
- [x] `core/bus.py` + `core/engine.py`: single-threaded, seq-ordered deterministic loop.
- [x] `core/determinism.py`: canonical JSON + sha256 hash-chain helpers.
- [x] `core/make_order.py`: the single `Order` constructor (calls risk gate later; stub gate returns APPROVE for now).
- [x] `core/config.py`: pydantic config; `mode` Enum = {backtest, paper} only; `execution.adapter` Enum = {paper} only; reject anything else at load.
- [x] `execution/_locked_out.py`: `NotImplementedError` stubs for any real broker adapter.
- **Tests:** replay-equality (two runs → identical audit hashes) · config rejects `mode: live` · `make_order` is the only `Order` constructor (AST/grep test) · hash-chain verifies · startup asserts `is_paper`.
- **Exit gate:** all safety + determinism tests green; run docs/archive/19 §19.1; `git tag m1-done`.

## M2 — Data ingest, validation, storage  · M · Dep: M1  ✅ `m2-done`
- [x] `data/base.py` (`MarketDataAdapter`) + `data/ccxt_adapter.py` (public endpoints only — no order methods anywhere).
- [x] `data/csv_replay.py`; `data/symbols.py` (canonical registry, survivorship-safe).
- [x] `storage/parquet.py` + `storage/catalog.py` (DuckDB: data_versions, symbols).
- [x] `data/validate.py`: all §8.4 checks (gaps, OHLC sanity, dupes, outliers, checksum) — fail loud, quarantine.
- [x] `data/ingest.py` + `cli lqe ingest`; `storage/replay_bundle.py` (frozen, checksummed).
- **Tests:** each validation check fires on injected bad data · idempotent ingest · no ccxt order method importable (safety) · replay bundle reproducible.
- **Exit gate:** ingest BTC-USDT/ETH-USDT to curated Parquet; validation + safety tests green; `git tag m2-done`.

## M3 — Model runtime + paper broker + backtest  · M · Dep: M1, M2  ✅ `m3-done`
- [x] `execution/paper_broker.py` (`is_paper=True`) + order state machine.
- [x] `execution/{fills,slippage,commission}.py` (pessimistic, next-bar-open default).
- [x] `portfolio/accounting.py` (Decimal, per-bar reconciliation) + `portfolio/sizing.py`.
- [x] `models/base.py` + one deterministic strategy (`trend_ma_cross`).
- [x] `backtest/make_session.py` (the shared loop) + `backtest/runner.py` + `cli lqe backtest`.
- **Tests:** end-to-end backtest deterministic (identical audit hashes) · accounting reconciles (cash+positions==equity) · fills never use future data (bar-completeness) · parity (replay==backtest decisions).
- **Exit gate:** `lqe backtest` runs on a real crypto bundle deterministically; `git tag m3-done`. → **ship v0.1 after M4.**

## M4 — Validation stack (the promotion gate)  · L · Dep: M3  ← the real product  ✅ `m4-done`
- [x] `analytics/metrics.py` + `dsr.py` + `pbo.py` (self-contained numpy).
- [x] Walk-forward runner; cost-sensitivity sweep (0/5/10/20 bps); benchmark set (buy-hold, equal-weight, best-single, random-entry).
- [x] `analytics/registry.py` (experiments/trials table with full provenance: config, data_version, git sha, seed, trial index).
- [x] `autonomy/validator.py` + `autonomy/promotion_gate.py`: `PromotionGate.check(candidate) → PASS/FAIL + evidence`; **trial-counting** feeds DSR/PBO.
- [x] `analytics/tearsheet.py` (markdown/HTML, "no profitability claimed" disclaimer).
- **Tests:** DSR/PBO correct on known inputs · gate FAILs an overfit candidate · gate PASSes a robust synthetic · trial count spans all trials/models · LLM/author cannot set `validated`.
- **Exit gate:** a candidate can be promoted **only** via the gate, with evidence recorded; `git tag m4-done`. **→ v0.1 (headless honest loop) shippable.**

## M5 — Risk model + kill/freeze + recovery  · M · Dep: M3  ✅ `m5-done`
- [x] `risk/model.py` + `risk/rules.py`: per-order + book-level checks (tunable-in-sim, audited) — single gate before `make_order`.
- [x] `risk/kill_switch.py`: persistent, disk-backed, human-owned, un-overridable by the LLM; survives restart.
- [x] Reconciliation each bar + on shutdown (halt on mismatch); rebuild-from-audit on restart.
- [x] De-risk action (cut exposure / pause / retire).
- **Tests (property):** no intent sequence breaches limits · kill ⇒ no risk-increasing order until human clears · reconciliation halts on injected mismatch · rebuild-from-audit reproduces state.
- **Exit gate:** risk gate + kill + recovery all enforced and tested; `git tag m5-done`.

## M6 — Model catalog + adapters + intake  · L · Dep: M3, M4  ✅ m6-done
- [x] Manifest schema + plugin discovery + intake checklist + quarantine list ([`03`](03-model-catalog.md)).
- [x] Library adapters: `IndicatorRuleAdapter` (native, replaces the rejected `PandasTaRuleAdapter` — see `pyproject.toml`), `SkfolioOptimizerAdapter`, `PyPortfolioOptAdapter`, `RiskfolioAdapter`, `StatsmodelsPairsAdapter`, `ArchVolAdapter`.
- [x] Ship ≥10 concrete models across the 4 families (trend, momentum, mean_reversion, volatility); each with manifest + tests + a passing Research backtest.
- [x] Heavy libs (statsmodels/arch/skfolio/PyPortfolioOpt/riskfolio-lib) in the `models` extra, lazily imported; runtime license gate green.
- **Tests:** adding a model = folder passing intake · adapters produce deterministic strategies · quarantine transparent (incl. the 5 heavy-lib adapters, which quarantine cleanly when `.[models]` isn't installed) · license gate green.
- **Exit gate:** ✅ 11 models listed + backtestable + gate-eligible; `git tag m6-done`.

## M7 — Obsidian Desk web UI (localhost, no CLI)  · L · Dep: M4, M5, M6  ✅ m7-done
- [x] FastAPI + Jinja2 + native Starlette WebSocket on `127.0.0.1` (NiceGUI rejected — its `docutils`/`bidict`/`orjson` chain fails the tiered license gate; see `pyproject.toml`); theme layer = the design tokens ([`05`](05-ui-and-3d-visualization.md), [`archive/28`](archive/28-ui-ux-design-system.md)); Inter + JetBrains Mono self-hosted with a system fallback (no CDN — localhost-only).
- [x] Views: Floor (model cells), Catalog, Research (backtest + gate evidence), Risk, Daily report.
- [x] **No CLI/stdout in the GUI** → honesty banners, tables/KPIs, a structured Tape (one row per audit event); asserted by a honesty test.
- [x] KILL/freeze control via `live.control` (the only write path); `storage.state_reader` (read-only); WebSocket live updates; honesty layer everywhere (SIMULATED + PAPER·LIVE LOCKED + sample sizes + unproven/validated).
- **Tests:** ✅ UI renders no unstructured stdout · kill flips the persistent switch + blocks risk-increasing orders · UI constructs no `Order`, imports no risk/execution/autonomy internals (AST) · bound to 127.0.0.1 only.
- **Exit gate:** ✅ app matches the Obsidian Desk mockup, no CLI feed, honesty overlays present; `git tag m7-done`. **→ v0.2 shippable.**

## M8 — Autonomy loop  · L · Dep: M4 (+M3, M2)  ← never before M4  ✅ m8-done
- [x] `autonomy/orchestrator.py` (rule-based OBSERVE→HYPOTHESIZE→SEARCH→VALIDATE→DECIDE→NARRATE) + `autonomy/optimizer.py` (**Optuna**, seeded `TPESampler`) + wires `Validator`/`PromotionGate`; every id is model+step-derived so the audit chain replays exactly.
- [x] `autonomy/drift.py` → degradation flags + de-risk-then-revalidate response ([`02`](02-autonomy-autopilot-and-learning-loop.md) §2.4). Implemented natively (deterministic two-window/flatness/drawdown, ADWIN/DDM as the named reference) rather than pulling River — the loop must be deterministic/replayable and dep-light.
- [x] Sandbox vs tracked books (`autonomy/books.py`); promotion crosses only via the gate (`TrackedBook.promote` re-checks the PASS verdict), every step audited (`Hypothesis/Trial/Validation/Promotion/DeRisk/Narration` events); honest catalog-wide trial counting.
- [x] Rule-based orchestrator (no LLM yet); `lqe autopilot` runs it over a replay bundle.
- **Tests:** ✅ loop runs all phases, all audited + replayable · gate un-bypassable (strict thresholds → nothing promoted) · degradation de-risks then re-validates (failed re-validation leaves the tracked config untouched) · Optuna seeded/reproducible · sandbox≠tracked.
- **Exit gate:** ✅ autonomous rule-based loop promotes only gate-passed configs; audit persists + reloads + re-verifies; `git tag m8-done`.

## M9 — Autopilot + local LLM  · M · Dep: M7, M8  ✅ m9-done
- [x] Autopilot toggle (Intel view + status-rail) → AUTOPILOT_ON/OFF via the whitelisted `ControlPlane`; decision cards (hypothesis→search→validate→promote/kill) rendered read-only from the audit; take-the-wheel = toggle OFF; the human KILL forces autopilot off and is un-overridable.
- [x] `autonomy/narrator.py`: optional Ollama local LLM (loopback HTTP via stdlib — no new dependency) emitting **structured tool calls**; low temperature; every call logged as an `LlmCallEvent` (prompt+response+model+seed+temperature) for replay-of-record.
- [x] `autonomy/tools.py`: the five tool calls + a **fail-closed** parser — the safety boundary. No order/kill/validated tool exists, so the LLM cannot express them; malformed/dangerous output is dropped.
- [x] Rule-based fallback (default, deterministic, templated) when no LLM is present or reachable; LLM range proposals are clamped to safe refinements of the vetted defaults (`safe_search_space`).
- **Tests:** ✅ LLM emits only whitelisted calls (order/kill/validated dropped); cannot bypass the gate or clear the kill; app works with the LLM absent; determinism-of-record (LLM calls logged, rule-based path byte-identical + replayable).
- **Exit gate:** ✅ autopilot aggressive but paper-only + audited; LLM optional; `git tag m9-done`. **→ v0.3 shippable.**

## M10 — Interactive 3D neural-web + replay  · L · Dep: M7, M8  ✅ m10-done
- [x] `viz3d/neural_web.js` fed by `StateReader.graph()`: model nodes, meta-layer + feed nodes, sandbox vs tracked regions, data-flow / attention / promotion edges. Implemented as a **dependency-free `<canvas>` force-graph** rather than three.js/`3d-force-graph` — those aren't vendorable in this offline, no-CDN build; the canvas renderer meets the acceptance criteria and a vendor slot (`viz3d/vendor/`) is documented for the full WebGL swap.
- [x] **Interactivity:** pan (drag) · zoom (wheel) · click node → inspector · hover tooltip.
- [x] **Timeline scrubber:** `/api/graph?at_seq=` replays any point in the session deterministically from the audit log (`StateReader.graph(at_seq)`).
- [x] Honesty overlays (SIMULATED — NOT EDGE, sample sizes, validated-tracked vs exploratory-sandbox); `prefers-reduced-motion` → static layout.
- **Tests:** ✅ graph builds from audit state (honest node fields, tracked/sandbox regions, only honestly-derivable edges) · replay-at-seq deterministic + monotonic · view/viz3d construct no `Order` and send no control · honesty overlays present · empty audit → valid empty graph.
- **Exit gate:** ✅ interactive scene animates real state + replays deterministically; `git tag m10-done`. **→ v0.4 shippable.**

## M11 — Scale the catalog  · L · Dep: M6, M8
- [ ] Add advanced statistical models: cointegration/pairs (statsmodels), GARCH filters (arch), HMM/regime (hmmlearn/ruptures), portfolio (HRP/risk-parity/BL via skfolio/riskfolio), supervised/meta-labeling (sklearn/LightGBM, gated).
- [ ] Multi-instrument/basket accounting + survivorship-safe ranked universe for factor models.
- [ ] Scale toward 50+ via adapters; ensure trial-counting spans the whole catalog.
- **Tests:** multi-asset accounting reconciles · pairs/factor deterministic · multiple-testing count recorded · unproven models can't be ranked/validated until gated.
- **Exit gate:** 50+ models available, honestly gated; license gate green; `git tag m11-done`.

## M12 — Hardening, review & release  · L · Dep: all
- [ ] Consolidate `tests/safety` + `tests/honesty`; re-run docs/archive/19 §19.1 + honesty checklist with evidence.
- [ ] `scripts/license_gate.py` in CI (fail on GPL/Commons-Clause in runtime); generate `THIRD_PARTY_NOTICES.md`.
- [ ] Packaging: local run script; optional desktop window (pywebview) / installer (PyTauri) — verify localhost-only; verify local-LLM weight licenses if distributing.
- [ ] Backups for `data/`, `runs/`, `catalog.duckdb`; a one-command `lqe doctor` health check.
- [ ] Update `HANDOFF`/`README`; write a short user guide.
- **Tests:** full suite green; determinism/parity/replay hold; packaged app binds 127.0.0.1 only and places no real order.
- **Exit gate:** all gates green with evidence; packaged app runs; `git tag v1.0`. **→ v1.0 production-ready local app.**

---

## Cross-cutting tracks (run at EVERY milestone, not once)
- **Safety gate:** paper-only lockout · one `Order` constructor after risk · no broker SDK / ccxt order calls · kill un-overridable by LLM · PromotionGate un-bypassable.
- **Honesty gate:** GUI has no CLI/stdout · sandbox≠tracked · sample sizes + "simulated — not edge" on every live/intel surface · no profit language.
- **Determinism gate:** replay-equality + backtest↔paper parity in CI.
- **License gate:** `pip-licenses` fails the build on GPL/Commons-Clause in runtime deps.
- **Docs:** update the relevant `docs/` file with each change.

## Suggested Claude Code subagents (solo parallelization)
- `safety-reviewer` — vetoes any diff violating a safety gate; mandatory on `risk/`, `execution/`, `autonomy/`.
- `test-author` — writes property/parity/safety/honesty tests with each module.
- `research-methodologist` — enforces [`04`](04-validation-and-overfitting-protocol.md) on any model/gate work.
- `license-auditor` — runs `pip-licenses`, blocks copyleft/Commons-Clause.
- `ui-critic` — checks the GUI renders no CLI and matches the design tokens.

## Suggested Claude Code skills (project-local)
`add-model` (scaffold plugin + manifest + tests + intake) · `run-gate` (walk-forward + DSR/PBO + benchmarks + verdict) · `safety-check` (full lockout/honesty/determinism suite → pass/fail report) · `ingest-crypto` · `new-hypothesis`.

## Risk register & rollback
- Every milestone ends in a `git tag mN-done` — roll back to the last green tag if a milestone destabilizes.
- **Top execution risks** (full list [`09`](09-decision-log-risks-open-questions.md) §9.3): automated overfitting (mitigate: M4 gate before M8) · sandbox/tracked confusion (hard separation) · LLM overreach (structured calls, gate, kill) · determinism regressions (CI replay tests) · scope/motivation (thin-slice releases v0.1→v1.0).
- **Never** start M8 (autonomy) before M4 (the gate) is green — an autonomous loop without the judge is the single most dangerous ordering mistake.

## One-line summary
Build the spine `M0→M1→M2→M3→M4→M8` for a headless honest autonomous loop, ship thin slices `v0.1→v1.0`, gate every milestone on safety + honesty + determinism + license, and tag each so you can always roll back.
