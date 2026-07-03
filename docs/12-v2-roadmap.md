# 12 — v2 Roadmap (Solo + Claude Code)

Continuation of [`10-production-roadmap.md`](10-production-roadmap.md), which ends at **v1.0** (`M0`–`M12`, all shipped, tagged). This doc exists because v1.0 defined no roadmap beyond itself — v2's scope was chosen explicitly by the product owner on 2026-07-03: **productionize the live multi-model fleet, complete the model catalog, and harden the LLM path with real CI coverage.** Same discipline as v1.0 applies: one milestone per session, tests-first, self-review at every gate, commit + tag (`m13-done` … `mN-done`), never merge red.

> Scope note: v2 formalizes and hardens the **post-v1.0 extension** already built and verified live in the prior session (`scripts/run_live_fleet.py`, `live/live_feed.py`, `live/multi_model_runner.py`, `live/merge.py`, `autonomy/searchable_scaled.py` — see `COMPONENT-GUIDE.md` §11 and `HANDOFF.md` §1a for what already exists and was verified before this roadmap was written). v2 does not re-invent that work; it moves it from "owner-directed script" to "supported product surface," fills the one remaining catalog gap, and closes the CI coverage hole that manual verification left open.

## Critical path
`M13 → M14 → M15` (fleet becomes a real, resumable CLI feature) can run in parallel with `M16` (catalog completion is independent of the CLI work) — but `M17` (release) depends on all four being green.

## Release checkpoint
- **v2.0 — Productionized live fleet + complete catalog + hardened LLM path:** + M13–M17.

---

## M13 — Complete the model catalog (51/51)  · S · Dep: none
- [ ] Enable Windows long-path support (`LongPathsEnabled` registry key or equivalent) on this machine — **confirm with owner before editing the registry**, since it's a system-wide (not repo-local) change, even though it's reversible and standard for Python dev on Windows.
- [ ] Install the 3 remaining `models` extra packages blocked by the path limit: `skfolio`, `PyPortfolioOpt` (`pypfopt`), `riskfolio-lib`.
- [ ] Remove/update the `@_absent(...)`-decorated skip conditions in `tests/unit/test_heavy_lib_adapter_quarantine.py` that were added specifically for these 3 libs' absence, so the suite reflects a fully-installed environment without lying about what's present.
- [ ] Confirm `models/catalog_scale.py` admits 51/51 (currently 48/51) via `lqe catalog`.
- **Tests:** heavy-lib quarantine tests for skfolio/PyPortfolioOpt/riskfolio-lib now exercise the real adapters (not skip) · `lqe catalog` reports 51 admitted · license gate still green with the 3 new deps.
- **Exit gate:** `lqe catalog` shows 51/51; full suite + ruff + mypy + license gate green; `git tag m13-done`.

## M14 — `lqe live` CLI subcommand  · L · Dep: none (parallel to M13)
- [ ] Port `scripts/run_live_fleet.py`'s argument surface (`--exchange`, `--symbol`, `--timeframe`, `--poll-seconds`, `--lookback-bars`, `--starting-cash`, `--autonomy-every`, `--n-trials`, `--min-periods`, `--llm`, `--llm-model`, `--kill-switch`, `--port`, `--no-browser`) into a real `lqe live` subcommand in `src/lqe/cli.py`, reusing the existing argparse pattern from `lqe backtest`/`lqe autopilot` rather than the script's standalone argparse.
- [ ] Reuse `core/config.py` validation where the live-fleet parameters overlap existing config fields, instead of the script's ad-hoc argument validation.
- [ ] Keep every existing safety property intact: paper-only, single shared `RiskModel`/`KillSwitch`, localhost-only serving, fail-closed LLM parsing — no new order-construction path, no CLI/stdout inside the desk UI.
- [ ] Retire `scripts/run_live_fleet.py` once `lqe live` reaches parity (or leave it as a thin wrapper calling the new CLI entry point — decide based on what the port actually looks like, don't presuppose).
- **Tests:** `lqe live --help` documents all flags · a short integration test runs `lqe live` against a fake/replay feed for a few polls and confirms it produces the same audit shape as the script did · safety tests (localhost-bound, no live broker, kill-switch honored) pass against the new entry point.
- **Exit gate:** `lqe live` is a first-class subcommand with test coverage equal to what the standalone script had; `git tag m14-done`.

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
