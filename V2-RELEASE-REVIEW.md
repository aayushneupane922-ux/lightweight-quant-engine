# V2 Release Review — `lightweight-quant-engine` v2.0

The `docs/archive/19` §19.1 safety review + honesty checklist, re-run against
everything new in `docs/12-v2-roadmap.md` (M13–M16: catalog completion,
`lqe live` as a real CLI subcommand, `--out` persistence/resume, the
real-Ollama integration test, and the second CI lane). v1.0's own review
(`M12-RELEASE-REVIEW.md`) still stands for M0–M12 and isn't repeated here —
this file only covers what M13–M16 added or changed. Reproduce the whole
gate with:

```
./.venv/Scripts/pytest.exe -q                      # 312 passed, 8 skipped (6 quarantine-inversion pairs + 2 llm_integration, Ollama not running)
./.venv/Scripts/ruff.exe check .                    # All checks passed!
./.venv/Scripts/mypy.exe src scripts                # Success: no issues found in 112 source files
./.venv/Scripts/python.exe scripts/license_gate.py  # license_gate: PASS — 50 runtime dependencies OK
./.venv/Scripts/python.exe -m lqe.cli catalog       # 51/51 admitted, 0 quarantined
```

## §19.1 Safety / live-lockout review (scoped to M13–M16's new/changed code)

### 1. Live lockout

| Claim | Verdict | Evidence |
|---|---|---|
| No new code path can place a real order | **PASS** | Grepped `src/lqe/cli.py`, `src/lqe/live/live_feed.py`, `src/lqe/live/multi_model_runner.py`, `src/lqe/models/catalog_scale.py`, `scripts/run_live_fleet.py` for `create_order`/`cancel_order`/`withdraw`/`place_order`/`api_key`/`api_secret` — zero hits. `lqe live --adapter ccxt` uses `CcxtMarketDataAdapter` (public OHLCV only), `--adapter csv` uses `CsvReplayAdapter` — neither has an order-capable method (existing `tests/safety/test_no_order_capable_data_adapter.py` still covers both, unchanged) |
| `PaperBroker` is still the only broker in the live-fleet path | **PASS** | `src/lqe/live/multi_model_runner.py:41` imports `PaperBroker`; `build_fleet` (`multi_model_runner.py:85`) constructs one per `ModelBook`. No other broker type referenced in `_cmd_live` or `multi_model_runner.py` |
| `make_order` is still the sole `Order` constructor on this path | **PASS** | `src/lqe/live/multi_model_runner.py:193` — the only `make_order(...)` call site in the live-fleet code; grep for bare `Order(` construction in the same files: zero hits. Pre-existing AST test `test_make_order_is_the_only_order_constructor` still covers the whole repo, unchanged |
| `lqe live`'s new `--out`/resume path introduces no new order-construction seam | **PASS** | `AuditLog.from_jsonl` (resume) only *reads* a persisted audit and replays `MarketEvent`s through the existing `runner.process_bar` loop — it does not construct or replay `Order`s directly; every `Order` on replay is still produced by the same `make_order` call site above, re-derived by the strategy/risk pipeline, not deserialized from the log |

### 2. Risk gate

| Claim | Verdict | Evidence |
|---|---|---|
| Every live-fleet order intent still passes through `RiskModel.check` before `make_order` | **PASS** | `src/lqe/live/multi_model_runner.py:189–193` — `decision = self.risk_model.check(...)` immediately precedes `make_order(intent, decision)`; a REJECT verdict `continue`s before `make_order` is ever called (line 191) |
| The fleet-wide aggregate risk state still reaches `RiskModel.on_bar` | **PASS** | `multi_model_runner.py:246` `self.risk_model.on_bar(aggregate_state)`, called once per bar from `_emit_aggregate_risk_state` — unchanged by M13–M16, re-verified via `tests/integration/test_live_multi_model_runner.py` (still green, 5 tests) |
| Only one `RiskModel`/`KillSwitch` pair serves the whole fleet (no per-model risk bypass) | **PASS** | `_cmd_live` constructs exactly one `KillSwitch` and one `RiskModel(kill_switch=kill_switch)`, passed into a single `LiveMultiModelRunner` shared by every `ModelBook` in the fleet — same pattern as the pre-M13 script, unchanged in the port |

### 3. Kill switch

| Claim | Verdict | Evidence |
|---|---|---|
| The live fleet's kill switch still halts every model's new entries at once | **PASS** | Unchanged code path (`RiskModel.check` reads `kill_switch.active`); pre-existing `tests/safety/` kill-switch suite (17 tests) re-run green against the current tree |
| `--out` resume does not let a stale kill-switch state override the *current* human decision | **PASS (by design, documented limitation)** | Resume reconstructs trading state from the persisted audit; the kill switch itself is a *separate*, independently disk-persisted file (`--kill-switch <path>`) read fresh at each `_cmd_live` invocation — a resumed run always uses the CURRENT kill-switch file's state, never a value baked into the replayed audit. Documented caveat (`docs/12-v2-roadmap.md` M15, `COMPONENT-GUIDE.md` §8): if a human toggles the kill-switch file *during* the gap between a crash and a resume, replayed historical decisions use the current (not historical) state for that window — this can only diverge in that specific edge case, and never lets the LLM/autonomy loop touch the switch |
| The LLM/autonomy tool vocabulary still has no kill/clear/order tool | **PASS** | `autonomy/tools.py` unchanged by M13–M16 (5 tools: propose_space/run_trials/promote_if_valid/de_risk/narrate); `tests/safety/test_llm_tools.py` still green |

### 4. Determinism / audit

| Claim | Verdict | Evidence |
|---|---|---|
| Replaying the same historical bars reproduces byte-identical audit hashes | **PASS** | `tests/integration/test_cli_live.py::test_lqe_live_resumes_byte_identical_state_from_the_same_out_path` — runs `lqe live` twice against the same `--out` path and asserts `head_hash`, every per-record `hash`, and every `payload` are identical between the two runs (excluding `event_id`/`wall_ts`, which `core/engine.py` documents as real non-deterministic metadata excluded from the hash by design) |
| The persisted trading audit hash-chain verifies on load, and a corrupted one fails loud | **PASS** | `AuditLog.from_jsonl` (used by the new resume path) raises `ValueError` on a failed `verify()` — same fail-loud behavior as the pre-existing M5 rebuild-from-audit pattern; not weakened for the new call site |
| Nothing in the decision path depends on wall-clock time (a prerequisite for replay to be deterministic at all) | **PASS** | Grepped `src/lqe/risk/model.py`, `risk/rules.py`, `execution/*.py`, `portfolio/*.py` for `datetime.now`/`time.time`/`utcnow` — zero hits |

**§19.1 result: PASS on every item scoped to M13–M16.**

## Honesty checklist (docs/10 cross-cutting honesty gate, re-checked for M13–M16)

| Claim | Verdict | Evidence |
|---|---|---|
| The catalog's new 51/51 admission is honestly reported, not overclaimed | **PASS** | `lqe catalog` output: "admitted (constructible now): 51 ... quarantined: 0"; every admitted model is still `unproven` until a gate PASS (`CatalogModelInfo(..., status="unproven")` in `_cmd_live`, unchanged pattern from the pre-M13 script) |
| The M14 bug fix (2-asset skfolio universe) is disclosed, not silently patched | **PASS** | Documented in `docs/12-v2-roadmap.md` M14, `COMPONENT-GUIDE.md` §11, and this file — described as a real latent bug found while running the fleet for real, not glossed over |
| `lqe live --out` resume's scope limitation is disclosed | **PASS** | `docs/12-v2-roadmap.md` M15, `HANDOFF.md` §5, `COMPONENT-GUIDE.md` §8 all state plainly that only the trading fleet is reconstructed, not the orchestrator's autonomy/promotion history |
| The `models-extra` CI job's unverified-on-a-live-runner status is disclosed | **PASS** | `docs/12-v2-roadmap.md` M16 and `HANDOFF.md` §5 both state this repo has no git remote, so the job is YAML-validated + locally-equivalent-verified but not yet run by GitHub Actions — not claimed as CI-proven when it isn't |

## License gate

- `models-extra`'s CI job installs `.[ui,search,dev,models]`; the `models` extra remains a non-promoted extra (`PROMOTED_EXTRAS = ("ui", "search")` in `scripts/license_gate.py`, unchanged), so the license gate's scanned closure is unaffected by M13's new heavy-lib installs. Output unchanged: `license_gate: PASS — 50 runtime dependencies (full transitive closure) OK.`

## Verdict

All safety, honesty, determinism, and license gates PASS with evidence for
everything M13–M16 added. Two documented, non-safety-weakening limitations
carried forward (resume doesn't cover autonomy history; `models-extra` CI
job unverified on a live runner) — both disclosed, neither silently assumed
away. **Cleared for `git tag v2.0`.**
