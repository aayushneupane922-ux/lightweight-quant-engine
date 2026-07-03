# HANDOFF — `lightweight-quant-engine`

**Purpose:** orient a developer (human or a fresh Claude Code session) picking this up cold. Read this, then `CLAUDE.md` (constitution) + `GUARDRAILS.md` + `WORKFLOW.md`, then `docs/10-production-roadmap.md` (the milestone map, kept checked-off as work lands).

## 1. Status (as of M11 complete)

A **local, paper-only, autonomous quant-research simulator** — built milestone by milestone against the `docs/` spec. **M0 through M11 are complete, verified, committed, and tagged; M12 (hardening + release → v1.0) is the only milestone left.**

- **Tags:** `m0-done` … `m11-done`, plus `v0.1`. (v0.2/v0.3/v0.4 were marked "shippable" in the roadmap at m7/m9/m10 but only the milestone tags were cut; `v0.1` was tagged on explicit request.)
- **Health:** **273 tests pass** · `ruff` clean · `mypy --strict` clean · license gate PASS · git tree clean.
- **Branch:** `master`. Every milestone = one commit + a `mN-done` tag. Git identity is a local placeholder (set per-repo, flagged to the owner).

### Verify everything in one shot (Windows, from repo root)
```
./.venv/Scripts/pytest.exe -q
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/mypy.exe src scripts tests      # CI runs `mypy src` only
./.venv/Scripts/python.exe scripts/license_gate.py
```
CI (`.github/workflows/ci.yml`) installs `.[ui,search,dev]` — **not** `.[models]` (the heavy-lib quarantine tests require those absent).

## 2. What's built (milestone by milestone)

- **M0** — repo scaffold, `pyproject.toml`, venv, ruff/mypy/pytest config, `scripts/license_gate.py`, CI.
- **M1** — deterministic core: hash-chained `AuditLog`/`Engine`, `Clock`/`ReplayClock`/`WallclockClock`/`ManualClock`, frozen event payloads (`core/events.py`), `make_order` (the sole `Order` constructor), config lockout (`mode: live` rejected), `LIVE_TRADING_ENABLED=False`.
- **M2** — data: ccxt adapter (public only, no order methods), CSV replay, OHLCV validation (§8.4 checks), Parquet + DuckDB catalog, replay bundles, `lqe ingest`.
- **M3** — runtime: `Strategy` protocol + `trend_ma_cross`, `PaperBroker` (`is_paper=True`), fills/slippage/commission, `Accounting` (Decimal, multi-symbol), sizing, `Session`/`make_session`, `lqe backtest`.
- **M4** — the gate: `analytics/metrics|dsr|pbo` (self-contained numpy), `ExperimentRegistry`, `autonomy/validator` (walk-forward + cost sweep + benchmarks), `autonomy/promotion_gate` (sole `GateResult` constructor), tearsheet, `lqe validate`. Tagged `v0.1`.
- **M5** — risk: `risk/rules` (12 MVP rules), `risk/model`, disk-backed human `KillSwitch`, reconciliation + rebuild-from-audit, de-risk controller; risk gate wired into `Session`.
- **M6** — catalog: `ModelManifest`, `ModelCatalog` + intake/quarantine, **native numpy indicators** + `IndicatorRuleAdapter` (9 presets), 11 models across 4 families, 5 heavy-lib structural adapters (lazy-imported).
- **M7** — UI: FastAPI + Jinja2 + native WebSocket on `127.0.0.1`, Obsidian Desk theme, Floor/Catalog/Research/Risk/Daily views, structured Tape, `StateReader` (read-only), `live/control.ControlPlane` (whitelisted `ControlEvent`s), `lqe desk`.
- **M8** — autonomy loop: `OptunaOptimizer` (seeded), native `DriftMonitor`, `TrackedBook` (gate-guarded), rule-based `Orchestrator` (OBSERVE→…→NARRATE, deterministic, audited), `lqe autopilot`. Trial provenance persists (`--catalog`) and spans campaigns.
- **M9** — autopilot + LLM: `autonomy/tools` (5 structured tool calls + fail-closed parser), `autonomy/narrator` (rule-based default + optional Ollama via stdlib, graceful fallback), `LlmCallEvent` provenance, UI autopilot toggle + Intel decision cards + take-the-wheel.
- **M10** — 3D neural-web: `StateReader.graph(at_seq)` (`GraphPayload`, deterministic timeline replay), `viz3d/neural_web.js` (dependency-free canvas force-graph), `/engine` view + `/api/graph`.
- **M11** — scale: `models/catalog_scale.py` (**51 models** via presets × param grids + heavy adapters), 3 more adapters (HMM/change-point/supervised), `reconcile_basket` (multi-instrument), `portfolio/universe.py` (survivorship-safe), `lqe catalog`.

## 3. Key deviations from the named spec (all deliberate + flagged)

The spec names some tools that were replaced for a good reason — same "own the spine / don't add a dep you can't vet or obtain" ethos each time:

| Spec named | Shipped instead | Why |
|---|---|---|
| pandas-ta (M6 indicators) | native numpy indicators | pandas-ta hard-requires tqdm (was read as MPL-2.0-bulk under the *old* strict license policy) |
| NiceGUI (M7 UI) | FastAPI + Jinja2 + Starlette WS | NiceGUI pulls `docutils`/`bidict`/`orjson` — ambiguous/MPL licenses, unvendorable |
| River (M8 drift) | native deterministic `DriftMonitor` | determinism hard-rail + no scipy in the runtime closure |
| Ollama python client (M9) | stdlib `urllib` to the local Ollama HTTP API | no new dependency, loopback-only, graceful fallback |
| three.js / 3d-force-graph (M10) | dependency-free `<canvas>` force-graph | not vendorable offline/no-CDN; meets the acceptance criteria; `viz3d/vendor/` slot documented |

**License policy was corrected mid-build** (the owner supplied updated `GUARDRAILS.md` + `docs/11` §11.11): now **tiered, transitive, fail-closed** — MPL-2.0 is ALLOW (so `certifi`, tqdm are fine); `scripts/license_gate.py` walks the full runtime closure of the *promoted* extras (`ui`, `search`) and fails closed on unknowns. `THIRD_PARTY_NOTICES.md` is generated by `scripts/generate_third_party_notices.py`.

## 4. Architecture invariants (never break — enforced by `tests/safety`)

- **Paper-only:** no real-order call sites anywhere; `PaperBroker` is the only `ExecutionAdapter`; `assert_paper_only` runs in `Session.__init__`; config `Literal`s reject `live`.
- **Single choke points:** `make_order` is the only `Order` constructor; `PromotionGate` is the only `GateResult` constructor (both AST-enforced). `TrackedBook.promote` re-checks the PASS verdict.
- **Kill switch:** human-owned, disk-persisted, never auto-clears; clearing needs a named operator; the LLM/autonomy can never clear it or place/size an order (the tool vocabulary has no such tool — fail-closed parser).
- **Determinism:** identical inputs+seed → identical audit hashes; sessions + the autonomy loop replay from the log; `ManualClock` drives the orchestrator's `sim_ts`.
- **Layering (docs/11 §11.1, `tests/safety/test_module_layering.py`):** `core` imports nothing project-specific; `storage` never imports `data` (their only cross is `data.ingest → storage`); `ui` imports only `storage.state_reader` + `live.control` + `core` (plus the `ui/builder.py` composition seam → `models`); `ui` does not import `viz3d` (static mount only).
- **Honesty:** GUI renders no CLI/stdout; sandbox ≠ tracked; `simulated` flag + sample sizes + `unproven`/`validated` everywhere; no profit-language (checked in templates); nothing ranked `validated` without a gate PASS.

Run `docs/archive/19` §19.1 safety review after any milestone or any change touching `risk/`, `execution/`, `autonomy/`, or the lockout.

## 5. What's left — M12 (final milestone → v1.0)

Per `docs/10` M12:
- [ ] Consolidate `tests/safety` + `tests/honesty`; re-run §19.1 + honesty checklist with evidence.
- [ ] `license_gate.py` in CI (done — verify) + `THIRD_PARTY_NOTICES.md` (generator exists — verify current).
- [ ] Packaging: local run script; optional desktop window (pywebview) / installer (PyTauri) — **verify localhost-only**; verify local-LLM weight licenses if distributing.
- [ ] Backups for `data/`, `runs/`, `catalog.duckdb`; a one-command `lqe doctor` health check.
- [ ] Update `HANDOFF`/`README`; short user guide.
- **Exit gate:** all gates green with evidence; packaged app runs + binds 127.0.0.1 only + places no real order; `git tag v1.0`.

## 6. Known small item (not a blocker)
`lqe autopilot`/`lqe backtest` dump a raw `FileNotFoundError` traceback on a missing bundle instead of a clean error line + non-zero exit. Cosmetic; documented in the memory note `cli-missing-bundle-traceback`. Fix candidate for M12 polish.

## 7. Working style that's been followed (keep it up)
Tests-first; one milestone per session then STOP for review; real verification (run it, don't claim it); flag deviations loudly and get a decision when a NEVER/scope line is near; commit + `mN-done` tag at each exit gate. The owner periodically asks for a mid-build audit ("check everything is intact") — that's the §19.1 safety review + layering + full-gate + a completeness cross-check against the milestone exit criteria.
