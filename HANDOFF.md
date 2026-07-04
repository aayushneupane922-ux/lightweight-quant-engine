# HANDOFF — `lightweight-quant-engine`

**Purpose:** orient a developer (human or a fresh Claude Code session) picking this up cold. Read this, then `CLAUDE.md` (constitution) + `GUARDRAILS.md` + `WORKFLOW.md`, then `docs/10-production-roadmap.md` (the milestone map, kept checked-off as work lands).

## 1. Status (v2.0 shipped; v3.0 in progress — M21/5 done)

A **local, paper-only, autonomous quant-research simulator** — built milestone by milestone against the `docs/` spec. **M0 through M12 (v1.0)** and **M13 through M17 (v2.0, `docs/12-v2-roadmap.md`)** are complete, verified, committed, and tagged. **v3.0 (`docs/13-v3-roadmap.md`, M18–M22) is in progress: M18, M19, M20, and M21 are done and tagged; only M22 (hardening + release) is left.** v4.0 (`docs/14-v4-catalog-expansion.md`, M23–M26) is scoped but not started at all. See §1a/§1c.

- **Tags:** `m0-done` … `m12-done`, `v0.1`, `v1.0`, `m13-done` … `m17-done`, `v2.0`, then `m18-done`, `m19-done`, `m20-done`, `m21-done`.
- **Health:** full suite green (409 tests, 8 correctly skipped as of `m21-done`), ruff clean, `mypy --strict` clean (`src` + `scripts` + `run.py`), license gate PASS (50 runtime deps), git tree clean.
- **Release evidence:** `M12-RELEASE-REVIEW.md` (v1.0) and `V2-RELEASE-REVIEW.md` (v2.0, M13–M16) — both full §19.1 safety/honesty reviews with evidence. v3.0 doesn't have its own review yet — that's M22's job, not done until v3.0 tags. Runtime guide: `USER-GUIDE.md` (not yet updated for v3/M18–M21 — that's also M22's job per `docs/13`'s own plan). Deep-dive on every component: **`COMPONENT-GUIDE.md`** (also not yet updated for M18–M21 — same reason).
- **Branch:** `master`. Every milestone = one commit + a `mN-done` tag. Git identity is a local placeholder (set per-repo, flagged to the owner).

### 1a. v2.0: what shipped (docs/12-v2-roadmap.md)

`docs/10-production-roadmap.md` ends at M12 → v1.0 with nothing left; v2.0 is a **separate roadmap doc** (`docs/12-v2-roadmap.md`) the owner explicitly scoped after being asked (three areas, all approved) and asked to follow the same milestone discipline as v1.0 (tests-first, tag+commit per exit gate). It's now fully shipped:

- **M13 — model catalog complete (51/51).** Owner enabled Windows long-path support (elevated, `LongPathsEnabled=1`); the 3 previously-blocked portfolio packages (`skfolio`, `PyPortfolioOpt`, `riskfolio-lib`) installed cleanly. **Found and fixed a real latent bug while wiring the fleet for real in M14**: `catalog_scale.py`'s shared synthetic universe had only 2 assets, and skfolio's `HierarchicalRiskParity` always crashes with exactly 2 (`argmax of an empty sequence`) regardless of history length — never triggered before because all 3 portfolio adapters were quarantined until this milestone. Fixed by expanding the synthetic universe to 3 assets.
- **M14 — `lqe live` is now a real, tagged CLI subcommand**, not a standalone script. Ported `scripts/run_live_fleet.py`'s full flag surface into `src/lqe/cli.py` (`_cmd_live`), added `--adapter {ccxt,csv}` (offline/test seam, mirrors `lqe ingest`) and `--max-polls` (bounded runs). `scripts/run_live_fleet.py` is kept as a thin wrapper delegating to `lqe live` (not deleted) so `.claude/launch.json` and muscle memory both keep working.
- **M15 — `lqe live --out <path>` persists and auto-resumes.** Passing the same `--out` path on a later run reconstructs the fleet's positions/cash/working orders and the fleet-wide risk aggregate exactly as they were — by **replaying** the persisted `MarketEvent`s through the same deterministic per-bar pipeline (reusing the M1/M3 replay-determinism guarantee), not by hand-written state reconstruction. New `LiveFeed.resume_from(bars)` repositions the polling dedup cursor. Documented limitation: only the *trading* fleet is reconstructed — the orchestrator's own autonomy/promotion history is a separate engine by design and starts a fresh campaign on resume.
- **M16 — real-Ollama integration test + a second CI lane.** `tests/integration/test_ollama_narrator_live.py` talks to a genuine local Ollama server, gated by an actual reachability probe (auto-skips when absent, auto-runs when present — verified both states live this session). New `models-extra` CI job installs `.[ui,search,dev,models]` and runs the full suite, kept strictly separate from `check` (which still needs `.[models]` absent to prove the quarantine path).
- **M17 — docs updated for v2.0** (this file, `README.md`, `USER-GUIDE.md`, `COMPONENT-GUIDE.md`), and a final full-suite/lint/type/license verification before tagging `v2.0`.

**A roadmap now exists past v2.0** (see §1c) — the "ask the owner" note above is historical (it was true when written, resolved since).

### 1c. v3.0 in progress (docs/13-v3-roadmap.md, M18–M22)

The owner sent `DEVELOPER-HANDOFF.md` (a standalone, non-agent-jargon briefing of the whole project) to their developer and asked for an upgrade roadmap. The developer sent back two documents, both adopted verbatim (with v4's milestones renumbered to continue this repo's tag sequence): `docs/13-v3-roadmap.md` (M18–M22 — launch/UX/blotter/engine-room-conversation) and `docs/14-v4-catalog-expansion.md` (M23–M26 — measured catalog diversification). Commit `df450ad`.

**M18 (zero-CLI one-click launch) is done, tagged `m18-done` (`936254f`):**
- `run.py` rewritten as a real one-click launcher: builds kill switch/control plane/desk data/job manager, serves immediately, runs first-run setup (auto-ingest a small offline synthetic demo dataset if `data/catalog.duckdb` doesn't exist) in the background, opens the browser once ready.
- New `LaunchState` + a FastAPI middleware (`ui/app.py`) serve `onboarding.html` for every route until setup finishes — plain-language status, never raw stdout/a stack trace.
- New `src/lqe/ops/jobs.py` (`JobManager`): runs ingest/backtest/live start-stop in background threads via the *same already-tested* functions the CLI uses (`data.ingest.ingest`, `backtest.runner.run_backtest`, the newly-extracted `live.session.LiveSession`) — no new order-construction path. New `/api/jobs*` routes (a second write surface, clearly labeled apart from `/api/control`) + a Live Control panel on Floor + a Quick Backtest panel on Research.
- New `src/lqe/live/session.py` (`LiveSession`): extracted `cli._cmd_live`'s session logic so the CLI and `JobManager` share one implementation. Re-verified byte-for-byte unchanged against pre-extraction behavior (all of M14/M15's `lqe live` tests, including the byte-identical-resume test, still pass).
- Verified live against a real running server (not just tests): first-run auto-ingest completed, Floor rendered the control panel, a real HTTP call started all 51 models trading, stop cleanly halted it.
- 27 new tests. Full detail + exact file/test citations: `docs/13-v3-roadmap.md`'s M18 section.

**Post-M18 fix (system audit, this session):** the owner reported `run.py` "opens and closes in a nanosecond" on double-click. Root cause: Windows hands double-clicked `.py` files to whatever Python is file-associated — here, a bare system install with none of this project's dependencies — so it crashed on the first `lqe` import and the console closed itself instantly (real console windows opened by double-click close the moment the process exits, whether it succeeded or crashed). Confirmed: `.venv\Scripts\python.exe run.py` runs fine end-to-end (first-run auto-ingest → `ready: true`); the bare system `python` errors with `ModuleNotFoundError: No module named 'lqe'`. Fix: added `run.bat` (repo root) as the actual Windows double-click target — calls `.venv\Scripts\python.exe run.py` explicitly and pauses on a missing-venv or crash so the window never vanishes silently again. `run.py` itself is unchanged. Verified via `Start-Process .\run.bat` (the real double-click code path) reaching `ready: true`. Updated `README.md`/`USER-GUIDE.md`/`docs/13-v3-roadmap.md` to point at `run.bat` for Windows; `python run.py` remains correct for anyone already in an activated venv/terminal.

**M19 (institutional UI/UX polish) is done, tagged `m19-done`:** the owner answered the TradingView Lightweight Charts question — **vendor it**, not hand-roll. Highlights:
- Vendored `lightweight-charts.standalone.production.js` v5.2.0 (Apache-2.0, official npm distribution, hash-pinned) under `ui/theme/vendor/`, documented in its own `README.md` since the Python license gate can't see a static JS asset.
- New Floor **hero chart**: candlestick price + streaming equity area, both read straight off existing `MarketEvent`/`RiskStateEvent` audit records via new `StateReader.price_series()`/`.equity_curve()` (no new event type) and served via new `GET /api/chart/price`/`/api/chart/equity` (downsampled to ≤1000 points). Pause/resume control, big KPIs, an accessible data-table fallback, empty-state text before first data.
- **Fill-vs-outline candlesticks** (bullish hollow/outline-only, bearish solid) so the up/down distinction survives colorblindness, not hue alone.
- New **⌘K/Ctrl+K command palette** (built from the already-rendered nav DOM, so it can't drift) + **toasts** (`aria-live="polite"`) replacing blind reload-with-no-feedback on control/job actions.
- **A real AA-contrast audit** found `--mute` (the spec's literal `#6B7A90`) failed 4.5:1 on `--slab`/`--desk` (4.01-4.27:1) — fixed by lightening to `#7A88A8` (4.9-5.6:1, same hue). Added `:focus-visible` rings, sticky table headers, explicit tabular-nums on all four data tables, and a real emoji-denylist scan (found none — the existing ★/✓/✗/◇ glyphs are intentional, not emoji-as-icon).
- Found the Obsidian Desk tokens/layout were **already built to this spec since M7/M9/M10** — M19's real remaining work was the chart, the palette, toasts, and the contrast audit, not a redesign.
- 28 new tests, full detail + exact file/test citations: `docs/13-v3-roadmap.md`'s M19 section. Verified live against the real `lqe desk` server with `runs/desk-preview/audit.jsonl` (not just TestClient).

**M20 (live trade blotter) is done, tagged `m20-done`:**
- New **Blotter** view (`/blotter`, `F8` — nav updated) + the full order lifecycle: new `StateReader.blotter()` reconstructs intent → risk decision (APPROVE/CLAMP/REJECT + `rule_hits` + reason) → fill/partial/reject straight off `OrderIntent`/`RiskDecision`/`Order`/`FillEvent` already in the audit log — no new event type. One row per fill; a REJECTed (or approved-but-unfilled) intent gets exactly one no-fill row, so nothing silently vanishes.
- **Unmissable feedback**: a new fill flashes its Blotter row + toasts + pulses the matching Floor model cell (`data-model` attribute added); an optional Web-Audio beep, off by default, persisted via `localStorage`.
- **Honest empty state**: new `blotter_empty_state_reason()` — "Warming up", "0 promoted models — exploring in the sandbox", or "no signals in the last bars", computed deterministically from the same snapshot the rest of the desk reads, never a blank panel.
- **Verified trades genuinely flow** (the spec's own explicit ask): `tests/integration/test_live_blotter_flow.py` runs the *real* live fleet (offline CSV, a genuine up/down price cycle) and asserts real fills reach the blotter — passed on 4 separate runs, not flaky.
- New **reconciliation panel**: per-model net position + realized P&L + trade count, reusing the same FIFO lot accounting `model_cells()` already reads from — one source of truth.
- `/ws`'s live-push frame now carries `blotter` alongside `snapshot`/`tape`; `/api/blotter` mirrors the read-only JSON contract of `/api/tape`.
- 19 new tests + `/blotter` added to the existing honesty-check page list. Full detail + exact file/test citations: `docs/13-v3-roadmap.md`'s M20 section. Verified live against the real `lqe desk` server with `runs/desk-preview/audit.jsonl`: real fills rendered on the Blotter page, the nav/`F8` link worked, `/api/blotter` returned real lifecycle JSON, and a live WebSocket connection's first frame carried 15 real blotter rows.

**M21 (the "Engine Room" conversation feed) is done, tagged `m21-done`:**
- New **conversation/timeline feed** on `/intel` (added alongside the existing M9 decision cards, not replacing them): new `StateReader.conversation()` reconstructs a readable dialogue between named participants — **Strategist** (`HypothesisEvent`), **Optimizer** (`TrialEvent`s aggregated into one "Ran N trials — best Sharpe X (params)" card per hypothesis, never one message per trial), **Judge** (`ValidationEvent`), **Autopilot** (`NarrationEvent`), **Risk** (`ControlEvent`/`DeRiskEvent`) — straight off events already in the audit log, no new event type.
- **Color-coded, verdict-driven for the Judge**: the Judge's card carries a `verdict` field so its color is long/short by outcome, not a fixed hue — "the Judge is visibly the one who decides," confirmed by a test that promotion messages are attributed to the Judge, never the Strategist.
- **No code/JSON/cryptic IDs** in the default text (internal `hypo_id`/`candidate_id` are grouping keys only, never rendered); a native `<details>` disclosure reveals the Judge's evidence as plain text for power users.
- **Works without the LLM by construction**: `conversation()` reads `NarrationEvent.text` as-is regardless of which narrator wrote it — no LLM-specific code path exists to break.
- **Deterministic replay**: new `GET /api/conversation?at_seq=` + a timeline scrubber (same UX as the Engine 3D view's) — verified live that scrubbing mid-campaign correctly reproduces a partial trial count, not the final one.
- 18 new tests. **Verified live against a real `lqe autopilot` campaign** (not a synthetic fixture): built a real replay bundle, ran 3 real hypothesis cycles, served the resulting audit log, and confirmed the feed, the scrubber, and the kill control all worked end to end with real Sharpe/DSR/PBO numbers. Full detail: `docs/13-v3-roadmap.md`'s M21 section.

**Only M22 (v3 hardening + release) is left before `v3.0` tags.**

**v4 (`docs/14-v4-catalog-expansion.md`, M23–M26) is fully scoped but zero work has started.** It depends on nothing in v3, so it could in principle be worked in parallel/before v3 finishes if the owner wants — not assumed, ask.

### 1b. This machine's local environment state (not portable, not committed)

- **Ollama**: installed at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. Not running as a persistent background service on this machine as of the end of this session — start it manually (`ollama serve`, or the `ollama app.exe` tray app) before using `--llm`/the `llm_integration`-marked tests. Model pulled: `llama3.2:3b` (~2GB).
- **models extra: fully installed** (post-M13) — `statsmodels`, `arch`, `hmmlearn`, `ruptures`, `scikit-learn`, `lightgbm`, `skfolio`, `PyPortfolioOpt`, `riskfolio-lib` are all in `.venv`. `lqe catalog` shows 51/51 admitted, 0 quarantined, on this machine. `LongPathsEnabled=1` is now set in the Windows registry (a system-wide setting, not repo-local — a fresh machine needs this step repeated per `USER-GUIDE.md` §1 before the full `.[models]` install will succeed).
- **No servers running**: confirmed clean at the end of the M21 session (no stray `python`/`ollama` processes).
- **Demo artifacts**: `data/`, `runs/`, `.claude/launch.json` (has `desk`, `live-fleet`, and a `launcher` preview config pointing at the rewritten `run.py`) are local/untracked convenience state, not part of the shipped product. Note: the `preview_start` tool's config-name cache has repeatedly not picked up new/edited `launch.json` entries mid-session (recurred again in M19/M20/M21) — the reliable fallback used every time since M18 is a manual background `lqe desk`/`run.py` process + `curl`/a small Python client script against the real HTTP/WebSocket endpoints. Expect to need this workaround again next session.

### Verify everything in one shot (Windows, from repo root)
```
./.venv/Scripts/pytest.exe -q
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/mypy.exe src scripts tests      # CI runs `mypy src` only
./.venv/Scripts/python.exe scripts/license_gate.py
```
CI (`.github/workflows/ci.yml`) now has **two jobs**: `check` (installs `.[ui,search,dev]` — deliberately NOT `.[models]`, since the heavy-lib quarantine tests need those absent) and `models-extra` (installs `.[ui,search,dev,models]`, full suite, so the heavy adapters get real coverage too). This repo has no git remote, so `models-extra` is YAML-validated + locally-equivalent-verified but not yet run on a live GitHub Actions runner.

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
- **M13** — catalog complete: Windows long-path support enabled, `skfolio`/`PyPortfolioOpt`/`riskfolio-lib` installed. Catalog admits 51/51.
- **M14** — `lqe live` CLI subcommand (`--adapter {ccxt,csv}`, `--max-polls`); fixed the latent 2-asset skfolio HRP crash found while running the full fleet for the first time.
- **M15** — `lqe live --out <path>` persistence + auto-resume via deterministic replay; `LiveFeed.resume_from`.
- **M16** — real-Ollama marker-gated integration test (`tests/integration/test_ollama_narrator_live.py`) + a second CI job (`models-extra`) installing the full `models` extra.
- **M17** — docs updated for v2.0 (this file, `README.md`, `USER-GUIDE.md`, `COMPONENT-GUIDE.md`); §19.1 safety/honesty review re-run against M13–M16; full suite/lint/type/license verified green. Tagged `v2.0`.
- **M18** — zero-CLI one-click launch: `run.py` rewritten (one-click launcher + first-run auto-ingest), `ops/jobs.JobManager` (GUI-triggered ingest/backtest/live start-stop), `live/session.LiveSession` (extracted from `cli._cmd_live`, shared by CLI + JobManager), onboarding screen (`LaunchState` + middleware), Live Control panel (Floor) + Quick Backtest panel (Research). Docs (`USER-GUIDE`/`COMPONENT-GUIDE`) intentionally not yet updated for this — that's M22's job per `docs/13`'s own plan, not an oversight.
- **M19** — institutional UI/UX polish: vendored TradingView Lightweight Charts (owner's call) for a Floor hero chart (candlestick + streaming equity, fill-vs-outline colorblind-safe), new `StateReader.price_series`/`.equity_curve` + `/api/chart/*`, a ⌘K/Ctrl+K command palette, `aria-live` toasts, a real AA-contrast audit (fixed `--mute`), focus rings, sticky table headers, tabular-nums. Found the design system's tokens/layout already matched spec since M7-M10.
- **M20** — live trade blotter: new `/blotter` view (`F8`) + `StateReader.blotter()`/`.reconciliation()` reconstruct the full intent → risk decision → fill/reject lifecycle straight off events already in the audit log, one row per fill; unmissable feedback (flash/toast/Floor-cell-pulse/optional sound); an honest, deterministic empty-state reason; `/ws` now pushes blotter rows too. Verified the real live fleet's fills genuinely reach the blotter (not just a display test) via a dedicated real-fleet integration test.
- **M21** — "Engine Room" conversation feed: new `StateReader.conversation()` reconstructs a readable Strategist/Optimizer/Judge/Autopilot/Risk dialogue on `/intel` (alongside, not replacing, M9's decision cards), color-coded with the Judge's card verdict-driven (long/short by outcome); new `GET /api/conversation?at_seq=` + a timeline scrubber (same pattern as the Engine 3D view's). Verified against a real `lqe autopilot` campaign, including deterministic mid-campaign replay.

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

**Immediate next step: M22 (v3 hardening + release), `docs/13-v3-roadmap.md` — the last milestone before `v3.0` tags.** M18–M21 are all done. M22 is: extend `tests/safety`+`tests/honesty` to the M18–M21 surfaces, re-run the §19.1 safety/honesty review with evidence (`V3-RELEASE-REVIEW.md`), and update `USER-GUIDE.md`/`COMPONENT-GUIDE.md` for real (both have been deferred to this milestone by design since M18, not by oversight — check `docs/13`'s own M22 checklist for the exact scope before starting).

After v3.0 (or in parallel, if the owner prefers — see §1c): **v4
(`docs/14-v4-catalog-expansion.md`, M23–M26)** — measured catalog
diversification by return-driver sleeve, not headcount; a correlation-
curation intake step; a trial-count update to the promotion gate so the
bigger catalog doesn't manufacture false positives. Zero work started on
this yet.

Check `git tag -l` for the latest `mN-done` to see how far execution has
gotten past this file's own last edit — this section is not guaranteed to
be updated every milestone the way the roadmap docs (`docs/13`, `docs/14`)
are, which carry per-milestone evidence inline as work lands.

Some things v2.0 itself surfaced but deliberately left out of scope (not
addressed by v3 or v4 either — flag for a future v5 if still wanted):

- The orchestrator's own autonomy/promotion history is not reconstructed on
  an `lqe live --out` resume (M15's documented limitation) — only the trading
  fleet is. Extending resume to cover that would mean replaying the
  orchestrator's own step cadence too, a materially bigger change.
- The `models-extra` CI job (M16) is YAML-validated and locally-equivalent-
  verified, but this repo has no git remote, so it's never actually been run
  by GitHub Actions. Push access + a live run would close that gap.
- `lqe live --kill-switch` state isn't itself versioned against a resume — if
  someone toggles the kill-switch file between a crash and a resume, replay
  uses the *current* state, which could (only in that edge case) diverge from
  what was originally decided in that exact window (M15 risk register).

**None of the above may weaken a lockout, the gate, or the honesty rails.**

## 6. Resolved items (historical, kept for context)
- `lqe backtest`/`lqe autopilot` used to dump a raw `FileNotFoundError` on a
  missing bundle. Fixed in M12: `load_bundle` raises a typed
  `DataQualityError` and the CLI catches `LqeError` at the boundary → clean
  line + exit 1. Tests in `tests/integration/test_cli_ops.py`.

## 7. Working style that's been followed (keep it up)
Tests-first; one milestone per session then STOP for review; real verification (run it, don't claim it); flag deviations loudly and get a decision when a NEVER/scope line is near; commit + `mN-done` tag at each exit gate. The owner periodically asks for a mid-build audit ("check everything is intact") — that's the §19.1 safety review + layering + full-gate + a completeness cross-check against the milestone exit criteria.
