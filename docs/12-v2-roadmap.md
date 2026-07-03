# 12 — v2 Roadmap (Solo + Claude Code)

Continuation of [`10-production-roadmap.md`](10-production-roadmap.md), which ends at **v1.0** (`M0`–`M12`, all shipped, tagged). This doc exists because v1.0 defined no roadmap beyond itself — v2's scope was chosen explicitly by the product owner on 2026-07-03: **productionize the live multi-model fleet, complete the model catalog, and harden the LLM path with real CI coverage.** Same discipline as v1.0 applies: one milestone per session, tests-first, self-review at every gate, commit + tag (`m13-done` … `mN-done`), never merge red.

> Scope note: v2 formalizes and hardens the **post-v1.0 extension** already built and verified live in the prior session (`scripts/run_live_fleet.py`, `live/live_feed.py`, `live/multi_model_runner.py`, `live/merge.py`, `autonomy/searchable_scaled.py` — see `COMPONENT-GUIDE.md` §11 and `HANDOFF.md` §1a for what already exists and was verified before this roadmap was written). v2 does not re-invent that work; it moves it from "owner-directed script" to "supported product surface," fills the one remaining catalog gap, and closes the CI coverage hole that manual verification left open.

## Critical path
`M13 → M14 → M15` (fleet becomes a real, resumable CLI feature) can run in parallel with `M16` (catalog completion is independent of the CLI work) — but `M17` (release) depends on all four being green.

## Release checkpoint
- **v2.0 — Productionized live fleet + complete catalog + hardened LLM path:** + M13–M17.

---

## M13 — Complete the model catalog (51/51)  · S · Dep: none  ✅ `m13-done`
- [x] Enable Windows long-path support (`LongPathsEnabled` registry key) — done by the owner directly (elevated shell), confirmed via `Get-ItemProperty` before proceeding.
- [x] Install the 3 remaining `models` extra packages blocked by the path limit: `skfolio`, `PyPortfolioOpt` (`pypfopt`), `riskfolio-lib`. (Pulled in a large transitive chain — cvxpy, vectorbt, matplotlib, astropy, numba, plotly — and downgraded `pandas` 3.0.3→2.3.3; full suite still green after.)
- [x] `tests/integration/test_catalog_scale.py`'s `test_heavy_lib_models_quarantine_transparently_when_absent` made present-aware (`skipif` on full-install, mirroring the existing `test_heavy_lib_adapter_quarantine.py` pattern) rather than editing that file, since the quarantine-when-absent behavior it tests wasn't specific to these 3 libs; added a new always-relevant counterpart `test_all_51_models_admit_once_the_full_models_extra_is_installed`.
- [x] Confirmed `models/catalog_scale.py` admits 51/51 (was 48/51) via `lqe catalog`.
- **Tests:** ✅ full suite green (6 skips, all the now-inverted quarantine-vs-absent pairs) · `lqe catalog` reports 51/51 admitted, 0 quarantined · license gate green (models extra correctly NOT in the scanned runtime closure — `PROMOTED_EXTRAS = ("ui", "search")` by design, unchanged).
- **Exit gate:** ✅ `lqe catalog` shows 51/51; full suite + ruff + mypy + license gate all green; `git tag m13-done`.

## M14 — `lqe live` CLI subcommand  · L · Dep: none (parallel to M13)  ✅ `m14-done`
- [x] Ported `scripts/run_live_fleet.py`'s full argument surface into a real `lqe live` subcommand in `src/lqe/cli.py` (`_cmd_live`, lazy-imported like `_cmd_autopilot`/`_cmd_desk` so base install stays light). Added two new flags beyond the original script: `--adapter {ccxt,csv}` + `--csv-path` (offline/test seam, mirrors `lqe ingest`'s own `--adapter` choice) and `--max-polls` (bounded runs for tests/scripted demos; `None` default = run forever, unchanged production behavior).
- [x] Config validation stayed as direct argparse (no reuse of `core/config.py`'s `mode`/`execution.adapter` schema needed — the live-fleet args are polling/UI parameters, not engine-mode config; nothing here could express `mode: live`).
- [x] Every safety property intact: still `PaperBroker`-only, `make_order`-only, ccxt read-only, one shared disk-persistable `KillSwitch`. Full suite (incl. `tests/safety/`) green against the new entry point.
- [x] `scripts/run_live_fleet.py` kept as a thin compatibility wrapper (`cli_main(["live", *argv])`) rather than deleted — `.claude/launch.json`'s "live-fleet" config and anyone's muscle memory keep working; no duplicated logic to maintain.
- **Found and fixed a real latent bug while wiring the full fleet for real:** `models/catalog_scale.py`'s 3 portfolio adapters (skfolio/PyPortfolioOpt/riskfolio-lib, M13) shared a hardcoded 2-asset/4-point synthetic universe. skfolio's `HierarchicalRiskParity` crashes (`argmax of an empty sequence`) with exactly 2 assets regardless of history length — never caught before because all 3 were quarantined until M13, and M13's own smoke test only sampled native presets. Fixed by expanding the shared universe to 3 synthetic assets (confirmed all 3 optimizers succeed); this was the first time any of the 3 adapters ran end-to-end.
- **Tests:** ✅ `lqe live --help` (`tests/integration/test_cli_live.py`) · a bounded end-to-end run against a real-time-relative CSV fixture (`--adapter csv`, `--max-polls 2`) verifying 51/51 admitted, real seeding, and the desk serving, with no crash · `--csv-path` required-arg validation · full suite (309 tests) + ruff + mypy + license gate all green.
- **Exit gate:** ✅ `lqe live` is a first-class, tested subcommand; `git tag m14-done`.

## M15 — Live fleet state persistence across restarts  · M · Dep: M14
- [ ] Extend the existing rebuild-from-audit recovery pattern (M5: `risk/model.py` reconciliation + restart rebuild) to the multi-model fleet: on `lqe live` startup, if a prior audit log for this run exists, reconstruct every `ModelBook`'s state (positions, cash, working orders) from it instead of starting flat.
- [ ] Reconcile the fleet-wide aggregate risk state (`_emit_aggregate_risk_state`'s peak-equity/day-anchor tracking) from the rebuilt books, not from zero.
- [ ] Decide and document the resume trigger (same `--out` audit path passed again vs. an explicit `--resume` flag) — this is a real design fork, flag it to the owner rather than assuming.
- **Tests:** kill a running fleet mid-session, restart against the same audit log, assert every book's reconstructed state matches what it was immediately before the kill · a fresh `--out` path still starts flat (no false resume).
- **Exit gate:** a killed-and-restarted fleet resumes with byte-identical reconstructed state; `git tag m15-done`.

## M16 — Real-Ollama integration test + `.[models]` CI lane  · M · Dep: M9, M13
- [ ] Add a marker-gated integration test (e.g. `@pytest.mark.llm_integration`) that talks to a real local Ollama server (skipped by default — no CI runner has a local LLM; run manually or via a dedicated job) exercising `OllamaNarrator` end-to-end: real chat call, real structured-output `format` constraint, real `parse_tool_calls` fail-closed check on genuine model output.
- [ ] Add a second CI job (separate from the existing `.[ui,search,dev]` lane) that installs `.[models]` and runs the full suite, so the statistical/ML adapters (statsmodels/arch/hmmlearn/ruptures/scikit-learn/lightgbm, and after M13 the 3 portfolio optimizers too) get real automated coverage instead of `skipif`-skipping everywhere.
- [ ] Confirm the existing `.[ui,search,dev]`-only CI lane is untouched (the heavy-lib quarantine tests still need that lane's absence-of-`.[models]` to prove the fail-closed quarantine path).
- **Tests:** the new marker-gated LLM test itself (run locally against the real server, documented as non-CI) · new CI job goes green on a real run · original CI lane still green and still proves quarantine-when-absent.
- **Exit gate:** two CI lanes exist and are both green; a documented, runnable (if manual) real-LLM test exists; `git tag m16-done`.

## M17 — v2 hardening & release  · S · Dep: M13, M14, M15, M16
- [ ] Update `HANDOFF.md`, `README.md`, `USER-GUIDE.md`, `COMPONENT-GUIDE.md` to describe `lqe live` as a supported command (not a standalone script), the 51/51 catalog, and the two CI lanes.
- [ ] Re-run the docs/archive/19 §19.1 safety review + honesty checklist against everything new in M13–M16, same as every v1.0 gate.
- [ ] `lqe doctor` health check extended to cover the new subcommand's preconditions (Ollama reachable if `--llm` requested, catalog count, etc.) if that fits cleanly — don't force it if it doesn't.
- **Tests:** full suite green across both CI lanes; determinism/parity/replay hold; license gate green.
- **Exit gate:** all gates green with evidence; `git tag v2.0`. **→ v2.0 shippable.**

---

## Cross-cutting tracks (unchanged from v1.0, run at EVERY milestone)
- **Safety gate:** paper-only lockout · one `Order` constructor after risk · no broker SDK / ccxt order calls · kill un-overridable by LLM · PromotionGate un-bypassable.
- **Honesty gate:** GUI has no CLI/stdout · sandbox≠tracked · sample sizes + "simulated — not edge" on every live/intel surface · no profit language.
- **Determinism gate:** replay-equality + backtest↔paper parity in CI.
- **License gate:** `pip-licenses` fails the build on GPL/Commons-Clause in runtime deps.
- **Docs:** update the relevant `docs/` file with each change.

## Risk register & rollback
- Every milestone ends in `git tag mN-done` — roll back to the last green tag if a milestone destabilizes.
- **M13 risk:** enabling Windows long-path support is a system-wide registry change on this specific machine, not a repo change — confirm with the owner before touching the registry, and document it as a local-environment step (like the Ollama install) rather than a portable build requirement.
- **M15 risk:** state-reconstruction bugs are the most dangerous kind here (silently wrong resumed positions) — property-test the reconstruction against a variety of interrupted states, not just the happy path.
- **M16 risk:** a second CI lane installing `.[models]` must not accidentally start asserting the heavy libs are *always* present — keep the original quarantine-tested lane exactly as-is.

## One-line summary
Take the post-v1.0 live-fleet extension from "owner-directed script" to "supported, tested, resumable product feature," close the last catalog gap (51/51), and give the LLM/heavy-model path real CI coverage instead of manual-only verification — same milestone discipline as v1.0, tagged `v2.0` at the end.
