# HANDOFF — `lightweight-quant-engine`

**Purpose:** orient a developer (human or a fresh Claude Code session) picking this up cold. Read this, then `CLAUDE.md` (constitution) + `GUARDRAILS.md` + `WORKFLOW.md`, then `docs/10-production-roadmap.md` (the milestone map, kept checked-off as work lands).

## 1. Status (v1.0 shipped; post-v1.0 extensions layered on top)

A **local, paper-only, autonomous quant-research simulator** — built milestone by milestone against the `docs/` spec. **M0 through M12 are complete, verified, committed, and tagged. The project is at v1.0.** Since the v1.0 tag, further work added functionality the owner asked for directly (not from `docs/10`, which ends at M12) — see §1a.

- **Tags:** `m0-done` … `m11-done`, `m12-done`, plus `v0.1` and `v1.0`. No tag yet for the post-v1.0 work below.
- **Health:** **306 tests pass, 2 skipped** (the 2 skips are correct — see §1a) · `ruff` clean · `mypy --strict` clean (`src` + `scripts`) · license gate PASS (50 runtime deps) · git tree clean.
- **Release evidence:** `M12-RELEASE-REVIEW.md` (§19.1 safety + honesty checklist, every item PASS with a file:line / test / command citation, as of the v1.0 tag). Runtime guide: `USER-GUIDE.md`. Deep-dive on every component + how to operate/extend it: **`COMPONENT-GUIDE.md`** (written post-v1.0; more current than this file for "how does X work").
- **Branch:** `master`. Every milestone = one commit + a `mN-done` tag. Git identity is a local placeholder (set per-repo, flagged to the owner).

### 1a. Post-v1.0 extensions (owner-directed, not in `docs/10`)

`docs/10-production-roadmap.md` **ends at M12 → v1.0**. There is no formal M13+ in any doc. The next session should **ask the owner what "the roadmap" means going forward** rather than inventing milestones — the owner's last message said "move towards new version as per the roadmap," which may refer to a roadmap not yet shared, or an intent to define one together next session.

What's been added on top of v1.0 so far, most recent first:

1. **Live multi-model paper trading against real-time market data** (`scripts/run_live_fleet.py`, NOT part of the tagged `lqe` CLI). Every admitted catalog model gets its own isolated paper book; all share one hash-chained audit log and one kill switch. Polls a real public exchange (ccxt, no key) continuously. New modules: `live/live_feed.py`, `live/multi_model_runner.py`, `live/merge.py`, `autonomy/searchable_scaled.py` (broadens the autopilot's search surface from 3 to 10 native models). One addition to the shipped UI layer: `DeskData.set_state_reader` (lets a background loop swap in a fresh read-side snapshot so the desk updates live). Full writeup: `COMPONENT-GUIDE.md` §11.
2. **Local Ollama installed on this machine** (`winget install Ollama.Ollama`, model `llama3.2:3b` pulled — see §1b for exact state) so the narrator can use a *genuine* local LLM instead of only the rule-based fallback. Fixed two real bugs in `autonomy/narrator.py` found by testing against the real server (not by inspection): `num_ctx` bounds Ollama's default 131k-token context (which otherwise tries to allocate a KV-cache buffer large enough to crash an ordinary machine), and Ollama's structured-output `format` parameter (JSON schema mirroring `autonomy.tools.Narrate`/`ProposeSpace`) reliably gets a small local model to emit the exact whitelisted tool shape — `parse_tool_calls` still validates independently and still fails closed regardless.
3. **The `models` extra, statistical/ML subset installed** (`statsmodels arch hmmlearn ruptures scikit-learn lightgbm` — NOT the full `.[models]`, see §1b for why). Catalog admits 48/51 (was 42/51); the 2 heavy-lib quarantine tests for statsmodels/arch now correctly `skipif` (present) rather than assert absence — hence "306 passed, 2 skipped" above. CI is unaffected (still installs `.[ui,search,dev]`, so those 2 tests still run and pass in CI).

### 1b. This machine's local environment state (not portable, not committed)

- **Ollama**: installed at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`, runs as an auto-started Windows background service on `127.0.0.1:11434`. Model pulled: `llama3.2:3b` (~2GB). This is *this machine's* state, not part of the repo/venv — a fresh clone or a different machine won't have it.
- **models extra**: `statsmodels`, `arch`, `hmmlearn`, `ruptures`, `scikit-learn`, `lightgbm` are installed in `.venv` (not just declared in `pyproject.toml`'s `[models]` extra — actually `pip install`ed). The 3 cvxpy-based portfolio optimizers (PyPortfolioOpt/skfolio/riskfolio-lib) are **not** installed — their `jupyter-widgets`/`vectorbt` dependency chain trips Windows' 260-character path limit unless `LongPathsEnabled=1` is set (admin + reboot); documented in `USER-GUIDE.md` §1.
- **No servers running**: the live-fleet preview (port 8141) and the demo desk (port 8137) were both explicitly stopped at the end of the last session, and the background Python processes confirmed killed. `Ollama` itself is left running (it's an installed system service now, not an ad-hoc process this project spawned).
- **Demo artifacts**: `data/`, `runs/`, `.claude/launch.json` (has a `live-fleet` config pointing at `scripts/run_live_fleet.py`) are local/untracked convenience state from demos, not part of the shipped product.

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
- **M12** — hardening + release: `ops/health.py` (`lqe doctor` — read-only invariant check), `ops/backup.py` (`lqe backup`), clean typed CLI errors (missing bundle → clean line, not a traceback), `run.py` (one-command launcher + optional pywebview window, loopback-only), `M12-RELEASE-REVIEW.md` (§19.1 + honesty with evidence), `USER-GUIDE.md`. Tagged `v1.0`.

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

## 5. What's left

All twelve `docs/10` milestones are done and tagged — the roadmap as written
has nothing left. Everything since v1.0 (§1a) was owner-directed, not
roadmap-driven. Candidate next slices, **none decided, none in scope until
the owner says so**:

- Formalize the live-fleet script into the tagged `lqe` CLI (e.g. `lqe live`)
  if the owner wants it as a first-class, permanent command rather than a
  script — currently deliberately kept separate from the v1.0 surface.
- Persist the autopilot's tracked book across process restarts.
- A real-Ollama integration test behind a marker (today's narrator tests
  correctly use a fake/rule-based path; the real-server behavior was
  verified manually this session, not captured as a repeatable test).
- Wire the `models` extra into a separate CI lane so the heavy adapters get
  exercised there (kept out of the default lane on purpose — the quarantine
  tests need `.[models]` absent in that lane).
- Enable Windows long-path support and finish installing the 3 cvxpy
  portfolio optimizers (§1b) if the owner wants the full 51/51 admitted.
- Define what "next version" / "the roadmap" actually means — **ask the
  owner**; nothing here should be assumed.

**None of these may weaken a lockout, the gate, or the honesty rails.**

## 6. Resolved items (historical, kept for context)
- `lqe backtest`/`lqe autopilot` used to dump a raw `FileNotFoundError` on a
  missing bundle. Fixed in M12: `load_bundle` raises a typed
  `DataQualityError` and the CLI catches `LqeError` at the boundary → clean
  line + exit 1. Tests in `tests/integration/test_cli_ops.py`.

## 7. Working style that's been followed (keep it up)
Tests-first; one milestone per session then STOP for review; real verification (run it, don't claim it); flag deviations loudly and get a decision when a NEVER/scope line is near; commit + `mN-done` tag at each exit gate. The owner periodically asks for a mid-build audit ("check everything is intact") — that's the §19.1 safety review + layering + full-gate + a completeness cross-check against the milestone exit criteria.
