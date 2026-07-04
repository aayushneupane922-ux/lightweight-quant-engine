# V4 Release Review — `lightweight-quant-engine` v4.0

The `docs/archive/19` §19.1 safety review + honesty checklist, re-run against
everything new in `docs/14-v4-catalog-expansion.md` (M23: the diversification
framework + sleeves A–E/G–I/L/M; M24: the perp/funding data adapter + sleeve
F; M25: the correlation-curation report + this review). v1.0's, v2.0's, and
v3.0's own reviews (`M12-RELEASE-REVIEW.md`, `V2-RELEASE-REVIEW.md`,
`V3-RELEASE-REVIEW.md`) still stand for M0–M22 and aren't repeated here —
this file only covers what M23–M25 added or changed. v4.0 shipped **no new
UI surface** — it is a catalog/data-layer expansion only, so this review is
scoped accordingly (no new routes/pages to re-check, unlike v3.0's).
Reproduce the whole gate with:

```
./.venv/Scripts/pytest.exe -q                        # 570 passed, 7 skipped (heavy-lib quarantine-inversion pairs -- statsmodels/arch/pypfopt/skfolio/riskfolio/full-104 all installed, so their quarantine-path tests correctly no-op -- + 2 llm_integration if no local Ollama server is running; both pass instead when one is up). Either way, 0 failed.
./.venv/Scripts/ruff.exe check .                      # All checks passed!
./.venv/Scripts/mypy.exe src scripts run.py           # Success: no issues found in 127 source files
./.venv/Scripts/python.exe scripts/license_gate.py    # license_gate: PASS — 50 runtime dependencies (full transitive closure) OK
./.venv/Scripts/python.exe -m lqe.cli catalog         # 104/104 admitted, 0 quarantined
```

New test coverage added specifically for this review (M25's own
contribution, beyond M23/M24's own milestone-exit tests):
`tests/safety/test_v4_no_shorting.py` (runs every one of the 104 admitted
models through a real, adversarial up-then-down multi-symbol backtest and
asserts not a single `SignalEvent` ever carries `direction == "SHORT"` —
verifying the "long-only" claim repeated across every sleeve C/D/F
manifest, not just trusting the prose) and
`tests/integration/test_curation_report.py` (2 tests proving
`models/curation.py::correlation_curation_check` correctly flags a real,
constructed duplicate over genuine `Session`-backtested returns).

## §19.1 Safety / live-lockout review (scoped to M23–M25's new/changed code)

### 1. Live lockout

| Claim | Verdict | Evidence |
|---|---|---|
| The new `CcxtFundingRateAdapter` (M24) exposes no trading method, same as `CcxtMarketDataAdapter` | **PASS** | `tests/unit/test_funding_adapter.py::test_adapter_has_no_trading_methods` plus the repo-wide AST scan `tests/safety/test_no_order_capable_data_adapter.py::test_no_trading_method_anywhere_in_src` (scans all of `src/lqe`, not just this file) |
| The multi-symbol `Context.universe_closes`/`Session.run` extension (M23) introduces no new order-construction seam — a signal from a *foreign* symbol's bar is never turned into an order | **PASS** | `tests/integration/test_multi_symbol_context.py::test_a_signal_emitted_on_a_foreign_bar_is_discarded_not_ordered` — the entire risk/accounting/order pipeline (`_resolve_working_orders`, `_update_day_anchor`, `_emit_risk_state`, the signal→order path, the equity-curve append) stays gated behind `bar.symbol == self._symbol`, unchanged from the single-symbol case; `test_a_pure_single_symbol_stream_behaves_exactly_as_before` re-confirms zero behavior change for every pre-v4 caller |
| **Every one of the 104 catalog models is genuinely long-only** — none ever emits `direction == "SHORT"`, matching the honest simplification declared in every sleeve C/D/F manifest's `failure_modes` | **PASS** | `tests/safety/test_v4_no_shorting.py::test_no_model_in_the_full_scaled_catalog_ever_signals_short` — every admitted model run through a real, adversarial (up-trend then down-trend, plus a perp premium) multi-symbol backtest; zero `SHORT` signals across the whole catalog, verified via the real audit log, not asserted in prose |
| The new `ingest_funding_rates` pipeline (M24) constructs no `Order`/`PaperBroker`, references no credentials | **PASS** | `data/ingest.py::ingest_funding_rates` mirrors the pre-existing `ingest()` shape exactly (fetch → validate → write → catalog version); grepped for `api_key`/`api_secret`/`credential` — zero hits, same as v3.0's own check |

### 2. Risk gate & control plane

| Claim | Verdict | Evidence |
|---|---|---|
| Every new strategy (sleeve C/D/F, ~50 new models across M23/M24) still emits ordinary `SignalEvent`s through the exact same `Session._process_bar` → sizer → `RiskModel.check` → `make_order` pipeline as every pre-v4 model | **PASS** | None of M23/M24 touched `make_order`, `risk/rules.py`, or the signal→order path in `backtest/make_session.py` beyond the foreign-bar-observation branch (item 1 above); every new adapter's `on_market` returns plain `list[SignalEvent]`, same `Strategy` protocol every model has always implemented |
| The gate's trial-count already spans the growing catalog (62→104 models across M23/M24), so the multiple-testing correction doesn't need updating by hand | **PASS** | Re-confirmed from M23: `ExperimentRegistry.trial_count()` is a blanket `count(*)` over every trial ever recorded, and `Orchestrator._n_trials_context` re-queries it live at construction — `test_trial_count_spans_multiple_models` (pre-existing) still covers this; no code change was needed at either M23 or M24 |
| Every new model enters `unproven` and can only be ranked `validated` by a real `PromotionGate` pass | **PASS** | `test_every_admitted_model_is_unproven_until_gated` (pre-existing, re-verified against the 104-model catalog) |

### 3. Determinism / replay

| Claim | Verdict | Evidence |
|---|---|---|
| Every new adapter (stat-arb, funding-carry, basis-carry, cross-exchange-funding, Johansen) is deterministic — same config + seed replays identically | **PASS** | All are pure functions of observed bar/funding data plus fixed constructor arguments (forward-fill lookups, no runtime randomness); `test_admitted_models_run_a_deterministic_backtest` (pre-existing, samples across the catalog) and the dedicated per-sleeve hash-chain-verified backtests (`test_cross_sectional_backtest.py`, `test_stat_arb_backtest.py`, `test_funding_carry_backtest.py`, `test_funding_carry_real_data_pipeline.py`) all assert `session.engine.audit.verify()` |
| The funding-rate ingest pipeline is idempotent, same guarantee as OHLCV `write_bars` | **PASS** | `tests/unit/test_parquet_funding.py::test_write_is_idempotent` / `test_overlapping_write_merges_by_timestamp` — re-ingesting the same or overlapping range never duplicates rows |

**§19.1 result: PASS on every item scoped to M23–M25.**

## Honesty checklist (docs/10 cross-cutting honesty gate, re-checked for M23–M25)

| Claim | Verdict | Evidence |
|---|---|---|
| Every new model's manifest honestly declares its real limitations, never overclaiming | **PASS** | Every sleeve C/D/F manifest's `failure_modes` states the long-only simplification explicitly ("this engine's short path is untested" / "NOT a market-neutral carry harvest ... P&L is ordinary spot price movement"); `economic_rationale` never claims collected funding or realized carry P&L |
| The M24 exit gate's own "measurably low-correlation to directional sleeves" criterion was **not** met — and this is disclosed, not reframed | **PASS** | Measured `carry_basis` vs. directional-sleeve cross-group correlation = 0.4144, *higher* than the 0.3742 whole-catalog average in the same run — reported plainly in `docs/14-v4-catalog-expansion.md`'s M24 section, `HANDOFF.md` §1e, and this file, with the mechanical (not accidental) cause explained: no real short-selling means every sleeve F model's P&L is ordinary spot price movement |
| The M25 correlation-curation report's 47% "would-be-flagged" figure is not overstated as straightforward catalog redundancy | **PASS** | `docs/14` §3's write-up explicitly separates genuine near-duplicate parameterizations from short-window behavioral convergence (several conceptually distinct models happened to buy-and-hold identically within the ~1.4-day test window) — verified by hand (`naive_always_long` and `day_of_week_0` finish the test window with the *identical* position size) rather than reported as one undifferentiated number |
| No profitability claim is implied by any new diversification/curation measurement | **PASS** | Every script (`diversification_report.py`, `curation_report.py`) prints an explicit "diagnostic measurement on synthetic backtested data, not a claim about the (currently empty) tracked/promoted book" disclaimer; no model has been promoted in this local environment (demo bundle too small to clear the gate) |
| `DataNeeds.kind="OHLCV+FUNDING"` and the new `Family="carry"` value honestly describe a genuinely new data/technical category, not a relabeled existing one | **PASS** | `models/manifest.py`'s own comments explain why (funding/perp data is fetched by a different adapter and stored by a different Parquet schema than OHLCV; "carry" needs neither a price-spread pair nor a single-instrument indicator, distinct from every prior `Family` value) |

## License gate

- **Python runtime deps:** unchanged scan scope; `scripts/license_gate.py` output: `license_gate: PASS — 50 runtime dependencies (full transitive closure) OK.` No new runtime dependency was introduced across M23–M25 — every new adapter is either pure numpy ("own") or reuses an already-vetted optional-extra library (`statsmodels` for the Johansen adapter, already present for `pairs_ols`).
- **`THIRD_PARTY_NOTICES.md`:** regenerated against the current environment; no new license entries.

## Verdict

All safety, honesty, determinism, and license gates PASS with evidence for
everything M23–M25 added: the multi-symbol engine extension introduces no
new order-construction seam and is a strict no-op for every pre-v4 caller;
every one of the 104 catalog models is verified — not just declared — to be
long-only; the new funding-rate data pipeline is read-only, idempotent, and
credential-free; every new model's manifest is honest about its real
limitations, including two unflattering measured findings (M24's
carry-correlation shortfall and M25's window-dependent curation figure) that
are disclosed plainly rather than reframed. No new limitations were
introduced beyond the ones already carried forward and disclosed in
`V3-RELEASE-REVIEW.md` (resume doesn't cover autonomy history; the
`models-extra` CI job is unverified on a live runner, since this repo has no
git remote), plus the two new ones this review discloses above. **Cleared
for `git tag m25-done`, then `git tag v4.0`.**
