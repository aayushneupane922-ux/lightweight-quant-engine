# V3 Release Review — `lightweight-quant-engine` v3.0

The `docs/archive/19` §19.1 safety review + honesty checklist, re-run against
everything new in `docs/13-v3-roadmap.md` (M18–M21: the zero-CLI one-click
launcher + onboarding gate, the Obsidian Desk design system + Floor hero
chart + command palette, the live trade blotter, and the "Engine Room"
conversation feed). v1.0's and v2.0's own reviews (`M12-RELEASE-REVIEW.md`,
`V2-RELEASE-REVIEW.md`) still stand for M0–M17 and aren't repeated here —
this file only covers what M18–M21 added or changed. Reproduce the whole
gate with:

```
./.venv/Scripts/pytest.exe -q                        # 418 passed, 8 skipped (6 heavy-lib quarantine-inversion pairs -- statsmodels/arch/pypfopt/skfolio/riskfolio/full-51 all installed, so their quarantine-path tests correctly no-op -- + 2 llm_integration, Ollama not running). Both llm_integration tests pass instead when a local Ollama server happens to be up (420 passed/6 skipped that way) -- either way, 0 failed.
./.venv/Scripts/ruff.exe check .                      # All checks passed!
./.venv/Scripts/mypy.exe src scripts run.py           # Success: no issues found in 115 source files
./.venv/Scripts/python.exe scripts/license_gate.py    # license_gate: PASS — 50 runtime dependencies (full transitive closure) OK
./.venv/Scripts/python.exe -m lqe.cli catalog         # 51/51 admitted, 0 quarantined
```

New test coverage added specifically for this review (M22's own contribution,
beyond M18–M21's own milestone-exit tests): `tests/safety/test_v3_surfaces.py`
(11 tests: the GUI job launcher constructs no `Order`/`PaperBroker` and stays
out of `lqe.execution`/`lqe.autonomy`; the blotter's kill button is reachable
and its API is read-only; the conversation feed's API is read-only +
deterministically replayable and its JS never posts to a write path) and 6
new tests appended to `tests/honesty/test_ui_honesty.py` (blotter/intel carry
their own honesty tags; both surfaces show a reason instead of a blank panel
when empty; the conversation feed's *default* view — outside the power-user
`<details>` disclosure — leaks no cryptic internal IDs or raw JSON, verified
against a real autopilot campaign, not just a synthetic fixture).

## §19.1 Safety / live-lockout review (scoped to M18–M21's new/changed code)

### 1. Live lockout

| Claim | Verdict | Evidence |
|---|---|---|
| The GUI job launcher (`ops/jobs.py`, M18) constructs no `Order`/`PaperBroker` directly | **PASS** | AST-scanned in `tests/safety/test_v3_surfaces.py::test_job_manager_constructs_no_order_directly` — zero `Order(`/`PaperBroker(` call sites; every job (`start_ingest`/`start_backtest`/`start_live`) delegates to the exact same `data.ingest.ingest`/`backtest.runner.run_backtest`/`live.session.LiveSession` the CLI already used pre-M18, each of which routes through the single `make_order` choke point already covered by `tests/safety/test_make_order_lockout.py` |
| `ops/jobs.py` reaches no `lqe.execution`/`lqe.autonomy` internals directly | **PASS** | `test_job_manager_imports_no_autonomy_or_execution_internals` — zero such imports; its one sanctioned exception (`lqe.risk.kill_switch`, needed to thread the switch through to `LiveSession`) is documented in the module's own docstring and unchanged from M18 |
| The GUI "live" job only ever wires a *market-data* adapter, never an execution adapter | **PASS** | `test_job_manager_live_start_only_ever_wires_a_data_adapter` — `start_live()`'s `adapter`/`csv_path`/`exchange` params select `CsvReplayAdapter`/`CcxtMarketDataAdapter` only; no `execution_adapter`/`ExecutionAdapter` parameter exists on this surface at all |
| The blotter (M20) and conversation feed (M21) are reconstructed read-only from the audit log, no new `Order` path | **PASS** | Both `StateReader.blotter()`/`.conversation()` only read `EventEnvelope`s already in the log (`_on_OrderIntent`/`_on_RiskDecision`/`_on_Order`/`_on_FillEvent` for the blotter; `HypothesisEvent`/`TrialEvent`/`ValidationEvent`/`PromotionEvent`/`DeRiskEvent`/`ControlEvent`/`NarrationEvent` for the conversation) — repo-wide AST scan `tests/safety/test_ui_boundary.py` plus the blotter-specific `test_blotter_route_renders_from_state_reader_only_no_order_construction` both confirm `ui/data.py`+`ui/app.py` build no `Order` |
| No new route/adapter constructs or references broker credentials | **PASS** | Grepped `src/lqe/ops/jobs.py`, `src/lqe/live/session.py`, `run.py` for `api_key`/`api_secret`/`credential` — zero hits |

### 2. Risk gate & control plane

| Claim | Verdict | Evidence |
|---|---|---|
| The GUI-triggered live job still passes every intent through `RiskModel.check` before `make_order` | **PASS** | `LiveSession`/`multi_model_runner` are unchanged by M18–M21; `ops/jobs.py` is a new *caller* of that pipeline, not a new pipeline — `tests/integration/test_live_blotter_flow.py::test_live_fleet_produces_real_fills_that_reach_the_blotter` proves a real GUI-triggered live run still produces fills that reconcile correctly through the existing risk-gated path |
| The onboarding gate (M18) never bypasses or delays the safety gate — it only delays which *template* renders | **PASS** | `tests/safety/test_onboarding_gate.py` (pre-existing, re-verified green): the gate swaps `Model Floor` for a plain-language status screen while `LaunchState.ready` is `False`; `/api/launch-status` and static theme/viz3d mounts stay reachable throughout; no stdout/traceback ever renders |
| The blotter's and conversation feed's kill button is reachable from every new page | **PASS** | `test_kill_button_is_reachable_from_the_blotter` / `test_kill_button_is_reachable_from_the_engine_room` — both assert `id="kill-btn"` renders; it lives in the shared `base.html` status rail, so it is structurally present on every desk page, new or old |
| `/api/blotter` and `/api/conversation` are read-only (no write verb registered) | **PASS** | `test_api_blotter_is_read_only` / `test_api_conversation_has_no_write_method` — `POST` to either returns 404/405; `src/lqe/ui/app.py` registers only `@app.get` for both routes |
| The conversation feed's own JS (`paintConversation`/`loadConversation`/`initConversationScrubber`) never posts to a write path | **PASS** | `test_conversation_feed_js_never_posts_to_the_control_or_jobs_write_paths` — sliced exactly that function span in `desk.js` and confirmed no `POST`/`/api/control`/`/api/jobs` reference (the file's legitimate `POST`s to those two whitelisted endpoints, added across M9/M18, live in unrelated functions) |

### 3. Determinism / replay

| Claim | Verdict | Evidence |
|---|---|---|
| `/api/conversation?at_seq=` replays deterministically, same as the pre-existing `/api/graph` pattern | **PASS** | `test_api_conversation_is_read_only_and_supports_deterministic_replay` — against a real autopilot audit log, `at_seq=5` returns a strictly-smaller message set than the full replay, and requesting the same `at_seq` twice returns byte-identical JSON |
| The blotter's per-fill P&L is derived from the same accounting state the rest of the desk already reads, not a second parallel computation | **PASS** | `StateReader._on_FillEvent` snapshots `_StrategyAgg.realized` immediately before/after the existing `on_buy`/`on_sell` call (already run for `model_cells()`) — no new P&L formula introduced; `tests/unit/test_state_reader.py`'s blotter tests (9) verify per-row and reconciliation totals agree |

**§19.1 result: PASS on every item scoped to M18–M21.**

## Honesty checklist (docs/10 cross-cutting honesty gate, re-checked for M18–M21)

| Claim | Verdict | Evidence |
|---|---|---|
| Every page — including the 3 new ones (`/blotter`, `/intel`'s new feed, the onboarding screen) — still carries the `PAPER · LIVE LOCKED` shield and no raw console/stdout | **PASS** | `tests/honesty/test_ui_honesty.py`'s existing parametrized suite now covers `PAGES = [..., "/blotter", "/intel"]` (already extended for `/blotter` at M20, `/intel` at M21); still green |
| The blotter carries its own honest framing (`SIMULATED` tag, explicit "constructs no order" read-only disclosure) | **PASS** | `test_blotter_carries_its_own_simulated_tag_and_read_only_narration` |
| The Engine Room carries its own honest framing (`OBSERVE-ONLY` tag, explicit "LLM can neither size an order nor clear the kill" language) | **PASS** | `test_intel_carries_observe_only_tag_and_gate_language` |
| Both new surfaces show a plain-language reason instead of a blank panel when there's nothing to show yet | **PASS** | `test_blotter_shows_a_reason_when_empty_not_a_blank_panel` / `test_conversation_feed_shows_a_reason_when_empty_not_a_blank_panel` — `blotter_empty_state_reason()` (M20) and the conversation feed's own empty-state copy (M21) both render non-blank |
| The conversation feed's *default* (always-visible) view never leaks internal event-correlation IDs or raw JSON | **PASS** | `test_conversation_feed_renders_no_cryptic_ids_in_the_default_view` / `test_conversation_feed_carries_no_raw_json_blob` — run against a real `Orchestrator` campaign's rendered `/intel` HTML, with the power-user `<details>` disclosure (which legitimately surfaces the Judge's raw `evidence` dict, per the M21 spec's own "Details for power users") explicitly excluded from the scan, matching the design decision already pinned at the unit level in `tests/unit/test_state_reader.py::test_conversation_no_raw_json_or_cryptic_ids_in_default_text` |
| The launcher's onboarding screen never renders a stack trace even when a background job errors | **PASS** | `ops/jobs.py`'s `_run()` closures catch `Exception` and store `f"{type(exc).__name__}: {exc}"` as a plain status message (`# noqa: BLE001 - a designed error state, not a stack trace`), never re-raising into the request/response cycle |

## License gate

- **Python runtime deps:** unchanged scan scope from v2.0 (`PROMOTED_EXTRAS = ("ui", "search")`); `scripts/license_gate.py` output: `license_gate: PASS — 50 runtime dependencies (full transitive closure) OK.` `THIRD_PARTY_NOTICES.md` regenerated against the current environment (one incidental diff: `numpy` 2.2.6→2.4.6, license string now spelled out as `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` — still fully `ALLOW`-tier, confirmed by the gate re-passing).
- **Vendored TradingView Lightweight Charts v5.2.0 (M19):** not a pip package, so it is out of `license_gate.py`'s scan scope by construction (that scanner walks the *Python* dependency closure via `pip-licenses`). Confirmed by hand, same as the pre-existing `viz3d/vendor` (three.js/3d-force-graph) precedent: the vendored file's own leading comment block declares `Licensed under Apache License 2.0`, matches the upstream `lightweight-charts` package's real license, and is `ALLOW`-tier under the tiered policy (`docs/11` §11.11). Fully documented in `src/lqe/ui/theme/vendor/README.md` (license, SHA-256, why it's out of the automated scan, upgrade instructions) — this was done correctly at M19 and re-confirmed here, not newly added.

## Verdict

All safety, honesty, determinism, and license gates PASS with evidence for
everything M18–M21 added: the one-click launcher and its background job
runner introduce no new order-construction seam; the onboarding gate never
weakens or bypasses the safety core, only swaps which template renders; the
blotter and Engine Room conversation feed are both strictly read-only,
replay-deterministic, honestly labeled, and keep the human kill switch
reachable from every page; the vendored charting library is correctly
licensed and documented. No new limitations were introduced beyond the two
already carried forward and disclosed in `V2-RELEASE-REVIEW.md` (resume
doesn't cover autonomy history; the `models-extra` CI job is unverified on a
live runner, since this repo has no git remote to run it on). **Cleared for
`git tag v3.0`.**
