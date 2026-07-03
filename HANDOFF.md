# HANDOFF — `lightweight-quant-engine`

**Purpose:** orient a developer (human or a fresh Claude Code session) picking this up cold. Read this, then `CLAUDE.md` (constitution) + `GUARDRAILS.md` + `WORKFLOW.md`, then `docs/10-production-roadmap.md` (the milestone map, kept checked-off as work lands).

## 1. Status (v2.0 shipped; v3.0 in progress — M18/5 done)

A **local, paper-only, autonomous quant-research simulator** — built milestone by milestone against the `docs/` spec. **M0 through M12 (v1.0)** and **M13 through M17 (v2.0, `docs/12-v2-roadmap.md`)** are complete, verified, committed, and tagged. **v3.0 (`docs/13-v3-roadmap.md`, M18–M22) is in progress: M18 is done and tagged; M19–M22 are not started.** v4.0 (`docs/14-v4-catalog-expansion.md`, M23–M26) is scoped but not started at all. See §1a/§1c.

- **Tags:** `m0-done` … `m12-done`, `v0.1`, `v1.0`, `m13-done` … `m17-done`, `v2.0`, then `m18-done`.
- **Health:** full suite green (336 passed, 8 correctly skipped as of `m18-done`), ruff clean, `mypy --strict` clean (`src` + `scripts` + `run.py`), license gate PASS (50 runtime deps), git tree clean.
- **Release evidence:** `M12-RELEASE-REVIEW.md` (v1.0) and `V2-RELEASE-REVIEW.md` (v2.0, M13–M16) — both full §19.1 safety/honesty reviews with evidence. v3.0 doesn't have its own review yet — that's M22's job, not done until v3.0 tags. Runtime guide: `USER-GUIDE.md` (not yet updated for v3/M18 — that's also M22's job per `docs/13`'s own plan). Deep-dive on every component: **`COMPONENT-GUIDE.md`** (also not yet updated for M18 — same reason).
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

**M19–M22 not started.** Before starting M19 (institutional UI/UX polish), there's a real, undecided dependency call flagged in `docs/13` itself: whether to vendor **TradingView Lightweight Charts** (Apache-2.0, license-gate-clean) for candlestick/streaming charts, or keep the existing hand-rolled `<canvas>` approach used for the 3D neural-web. This was surfaced to the owner at the end of the M18 session but not yet answered — **ask before starting M19**, don't assume either way.

**v4 (`docs/14-v4-catalog-expansion.md`, M23–M26) is fully scoped but zero work has started.** It depends on nothing in v3, so it could in principle be worked in parallel/before v3 finishes if the owner wants — not assumed, ask.

### 1b. This machine's local environment state (not portable, not committed)

- **Ollama**: installed at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. Not running as a persistent background service on this machine as of the end of this session — start it manually (`ollama serve`, or the `ollama app.exe` tray app) before using `--llm`/the `llm_integration`-marked tests. Model pulled: `llama3.2:3b` (~2GB).
- **models extra: fully installed** (post-M13) — `statsmodels`, `arch`, `hmmlearn`, `ruptures`, `scikit-learn`, `lightgbm`, `skfolio`, `PyPortfolioOpt`, `riskfolio-lib` are all in `.venv`. `lqe catalog` shows 51/51 admitted, 0 quarantined, on this machine. `LongPathsEnabled=1` is now set in the Windows registry (a system-wide setting, not repo-local — a fresh machine needs this step repeated per `USER-GUIDE.md` §1 before the full `.[models]` install will succeed).
- **No servers running**: confirmed clean at the end of this session (`Get-Process python*,ollama*` empty).
- **Demo artifacts**: `data/`, `runs/`, `.claude/launch.json` (has `desk`, `live-fleet`, and now a `launcher` preview config pointing at the rewritten `run.py`) are local/untracked convenience state, not part of the shipped product. Note: the `preview_start` tool's config-name cache didn't pick up the new `launcher` entry mid-session (had to verify M18 manually via a background `python run.py` process + curl instead) — if that recurs, the same manual-verification approach works fine.

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

**Immediate next step: M19 (institutional UI/UX polish, `docs/13-v3-roadmap.md`).**
Before starting it, ask the owner the TradingView Lightweight Charts
vendoring question flagged in §1c — it was surfaced, not yet answered, at
the end of the M18 session. Don't assume either direction.

After M19: **M20 (live trade blotter)** and **M21 (engine-room conversation
feed)** — both depend on M19's design system, not on each other, so either
order works. Then **M22 (v3 hardening + release: safety/honesty re-review,
`V3-RELEASE-REVIEW.md`, docs updated for real this time, tag `v3.0`)**.

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
