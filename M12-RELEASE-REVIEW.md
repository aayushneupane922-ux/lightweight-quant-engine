# M12 Release Review — `lightweight-quant-engine` v1.0

The `docs/archive/19` §19.1 safety review + honesty checklist, re-run at the
M12 exit gate with evidence. Every PASS cites a file, a test name, or command
output. Reproduce the whole gate with:

```
./.venv/Scripts/pytest.exe -p no:warnings -q      # 291 passed
./.venv/Scripts/ruff.exe check .                   # All checks passed!
./.venv/Scripts/mypy.exe src                       # Success: no issues found in 104 source files
./.venv/Scripts/python.exe scripts/license_gate.py # license_gate: PASS — 50 runtime deps OK
./.venv/Scripts/python.exe -m lqe.cli doctor       # overall: OK (with an audit log + clear kill switch)
```

## §19.1 Safety / live-lockout review

### 1. Live lockout

| Claim | Verdict | Evidence |
|---|---|---|
| No code path can place a real order | **PASS** | Repo grep for `create_order`/`cancel_order`/`withdraw`/`place_order`/`api_key` finds only docstrings documenting the prohibition (`data/ccxt_adapter.py:3`, `data/base.py:3`) and the fail-closed tool-parser comment (`autonomy/tools.py:11`). Test: `tests/safety/test_no_order_capable_data_adapter.py::test_no_trading_method_anywhere_in_src` |
| `LIVE_TRADING_ENABLED` is False and cannot be flipped via config/env | **PASS** | `src/lqe/constants.py:15` (`LIVE_TRADING_ENABLED: bool = False`); config `mode` is a closed `Literal["backtest","paper"]` (`core/config.py:36`) and `_reject_live` refuses live/real/prod *by name* (`core/config.py:75`). Tests: `test_config_rejects_live_mode`, `test_load_config_rejects_live_mode_from_a_file` |
| Startup asserts `execution_adapter.is_paper` and refuses otherwise | **PASS** | `core/config.py:112 assert_paper_only`; wired in `Session.__init__`. Tests: `test_assert_paper_only_rejects_non_paper_adapter`, `test_session_refuses_a_non_paper_broker_at_construction` |
| Config schema rejects `mode: live` and non-paper adapters | **PASS** | Tests: `test_config_rejects_live_mode`, `test_config_rejects_non_paper_execution_adapter` |
| `PaperBroker` is the only `ExecutionAdapter` | **PASS** | `_LiveBrokerAdapter` in `execution/_locked_out.py` raises on instantiation. Tests: `test_live_broker_adapter_cannot_be_instantiated`, `test_paper_broker_satisfies_the_execution_adapter_protocol` |

### 2. Risk gate

| Claim | Verdict | Evidence |
|---|---|---|
| Exactly one function constructs `Order`, after a risk decision | **PASS** | `make_order` is the sole constructor (AST-enforced). Tests: `test_make_order_is_the_only_order_constructor`, `test_make_order_builds_an_order_after_approve` |
| No code can emit an `Order` without an APPROVE/CLAMP | **PASS** | `test_make_order_rejects_a_reject_decision` — a REJECT decision raises rather than returning an Order |
| Risk rules fail closed on bad/missing state | **PASS** | `risk/rules.py` (12 MVP rules); a stale/missing `last_data_ts` and kill-active both REJECT. Tests: `tests/unit/test_risk_model.py`, `test_kill_switch.py` |
| Only the `Validator` sets `validated` (`PromotionGate` sole `GateResult`) | **PASS** | `test_promotion_gate_sole_verdict.py`; `TrackedBook.promote` re-checks PASS |

### 3. Kill switch

| Claim | Verdict | Evidence |
|---|---|---|
| Once kill is set, no risk-increasing order is emitted | **PASS** | `test_kill_rejects_a_buy_but_allows_a_flattening_sell`, `test_kill_from_the_ui_blocks_a_risk_increasing_order` |
| Kill persists across restart and never auto-clears | **PASS** | `test_kill_switch_survives_a_restart`, `test_kill_switch_never_auto_clears_on_reload`, `test_kill_persists_until_explicitly_cleared` |
| Clearing needs a named operator; the LLM/autonomy can't clear it | **PASS** | `KillSwitch.clear` raises without an operator (`risk/kill_switch.py:40`). Tests: `test_clear_requires_a_named_operator`, `test_kill_forces_autopilot_off_and_is_un_overridable`. The tool vocabulary has no kill/clear/order tool (`autonomy/tools.py`, fail-closed parser) |

### 4. Determinism / audit

| Claim | Verdict | Evidence |
|---|---|---|
| Two identical runs produce identical audit hashes | **PASS** | `test_backtest_hash_chain_is_deterministic_across_runs`, `test_two_runs_same_seed_produce_identical_audit_chains` |
| The audit hash-chain verifies; the log is append-only | **PASS** | `test_hash_chain_verifies`, `test_hash_chain_detects_tampered_hash`, `test_hash_chain_detects_tampered_payload`; `AuditLog.from_jsonl` re-verifies on load (`core/engine.py:107`) |
| Sessions + the autonomy loop replay from the log | **PASS** | `test_audit_log_persists_and_replays_from_disk`, `test_replay_equality_same_run_id_same_hash_chain`, `test_replay_at_seq_is_monotonic_and_deterministic` |

**§19.1 result: PASS on every item.**

## Honesty checklist (docs/10 cross-cutting honesty gate)

| Claim | Verdict | Evidence |
|---|---|---|
| GUI renders no CLI/stdout — structured components only | **PASS** | `tests/honesty/test_ui_honesty.py` (17 tests); templates carry no raw log/stdout surface |
| Sandbox ≠ tracked; nothing is `validated` without a gate PASS | **PASS** | `test_ui_boundary.py`, `test_promotion_gate_sole_verdict.py`; every admitted catalog model is `unproven` until promoted (`lqe catalog` footer) |
| Sample sizes + `simulated`/`unproven`/`validated` labels present | **PASS** | honesty suite asserts the `simulated` flag + sample-size surfacing on live/intel surfaces |
| No profit language | **PASS** | honesty suite scans templates for profit/return-claim phrasing |
| `lqe doctor` reports the standing invariants honestly | **PASS** | `ops/health.py`; a tampered audit log → FAIL/exit 1 (`test_doctor_flags_a_tampered_audit_log`); an active kill switch → WARN |

## License gate + notices

- CI runs the gate: `.github/workflows/ci.yml:28` → `python scripts/license_gate.py`.
- Gate is tiered/transitive/fail-closed over the promoted extras (`ui`, `search`); output: `license_gate: PASS — 50 runtime dependencies (full transitive closure) OK.`
- `THIRD_PARTY_NOTICES.md` regenerated by `scripts/generate_third_party_notices.py` (50 packages); no diff → current.

## Packaging / localhost-only

- `lqe desk` and `run.py` both bind `127.0.0.1` only (`ui/app.py:30` `BIND_HOST`, `ui/app.py:180` `serve`). Guarded: `test_bind_host_is_localhost_only`, `tests/safety/test_run_script_localhost.py` (run.py has no routable bind literal).
- No auth by design (unreachable off loopback); no real order possible (lockout above).
- Optional desktop window (`run.py --window`, pywebview) and any local-LLM weights (Ollama) are **not bundled/distributed** — imported lazily, user-supplied; their licenses are the user's responsibility. No copyleft/weight license enters this repo's runtime closure.

## Verdict

All safety, honesty, determinism, and license gates PASS with evidence. The
packaged local app runs, binds loopback only, and can place no real order.
**Cleared for `git tag v1.0`.**
