# 13 — v3 Roadmap — Launch, Visibility & Institutional Polish (M18–M22)

Continuation of [`12-v2-roadmap.md`](12-v2-roadmap.md) (v2.0, fully shipped).
Four upgrades from real usage, proposed by the project's developer and
adopted as the next roadmap: (1) zero-CLI one-click launch, (2)
institutional UI/UX polish, (3) a live trade blotter you can actually watch,
(4) a plain-language "engine room" feed where you witness the LLM, the
ML/optimizer, and the autopilot talk to each other. Same discipline as v1/v2:
tests-first, an exit gate + `git tag mN-done` per milestone.

> **These are all additive UX/visibility. None of them touches the 9 safety
> non-negotiables (`GUARDRAILS.md` "NEVER" + "OUT OF SCOPE" sections /
> `docs/11`).** The UI stays **read-only + whitelisted control commands** —
> it must construct no `Order`, gain no new capability, and render no
> CLI/stdout. The honesty layer (simulated · sandbox-vs-validated · sample
> sizes) stays on every new surface. M22 re-proves all of this.

Grounded in: the `ui-ux-pro-max` + `frontend-design` design skills,
institutional-terminal/blotter UX research, and 2026 agent-UX research
(sources at the end).

---

## M18 — Zero-CLI, one-click launch  · M · Dep: v2.0  ✅ `m18-done`
**Goal:** the user double-clicks one thing; everything the CLI used to do
happens automatically, and they land on a ready dashboard. No terminal,
ever.

- [x] **Single entry point** (`run.py`, rewritten): builds a `KillSwitch` +
  `ControlPlane` + `DeskData` + `JobManager`, starts the FastAPI server on
  `127.0.0.1` in a background thread immediately, runs first-run setup in a
  second background thread (auto-ingests a small offline synthetic demo
  dataset via the same `JobManager.start_ingest` path the GUI's own
  "Ingest demo data" button uses, if `data/catalog.duckdb` doesn't exist
  yet), then opens the browser (or a native `pywebview` window with
  `--window`) once ready. A full desktop-installer/bundled-deps path
  (PyTauri) was judged out of scope for this milestone — `run.py` still
  requires a working `.venv`, same as `lqe doctor`/M12's launcher; noted as
  a real gap below, not silently assumed done. **Post-M18 fix:** real-world
  double-clicking `run.py` on Windows silently failed (Windows hands `.py`
  files to whatever Python is file-associated, usually a bare system
  install without this project's deps, so it crashed on the first import
  and the console closed itself instantly) -- added `run.bat` as the actual
  Windows double-click target, calling `.venv\Scripts\python.exe` explicitly
  and pausing on error/missing-venv so the window never vanishes silently.
  `run.py` unchanged; `run.bat` is a thin wrapper. Verified live via
  `Start-Process .\run.bat` (the double-click equivalent) -> server reached
  `ready: true`.
- [x] **Friendly onboarding/status screen**: new `LaunchState` (`ops/jobs.py`)
  + a FastAPI middleware in `ui/app.py` that serves `onboarding.html`
  (plain-language message, auto-polling `/api/launch-status`, no raw
  stdout/stack trace ever rendered) for every route until setup finishes,
  then transparently lets the real dashboard through — verified live (both
  a fresh first-run and an already-set-up run) and in
  `tests/safety/test_onboarding_gate.py` (6 tests).
- [x] **Every operation reachable from the GUI**: new `ops/jobs.JobManager`
  runs ingest/backtest/live-start/live-stop in background threads, calling
  the *exact same* already-tested functions the CLI uses
  (`data.ingest.ingest`, `backtest.runner.run_backtest`, the extracted
  `live.session.LiveSession` — see below) — no new order-construction path.
  New `/api/jobs*` routes (a second write surface from `/api/control`,
  clearly labeled as such) + a Live Control panel on Floor (Start/Stop
  Live, resume checkbox, Ingest demo data) + a Quick Backtest panel on
  Research (explicitly labeled as *not* the validation gate, to avoid
  implying it validates anything). Autopilot on/off was already
  GUI-reachable since M9 — untouched.
- [x] **`live/session.py` (`LiveSession`, new)**: extracted `cli._cmd_live`'s
  session logic (seed/resume, fleet/engine/orchestrator wiring, per-bar
  processing) into a reusable class so the CLI and `JobManager` share one
  implementation, not two that could silently drift. Re-verified byte-for-
  byte against the pre-extraction behavior: all of M14/M15's existing
  `lqe live` tests (including the M15 byte-identical-resume test) still
  pass unchanged after the refactor.
- [x] **Session control**: a "Resume last session if available" checkbox
  (checked by default) on the Live Control panel includes a conventional
  `--out`-equivalent path in the start request when checked, so clicking
  Start Live either begins fresh or resumes (M15's existing mechanism) —
  visibly reported back in the status message either way. Nothing
  auto-starts; the human must click Start.
- [x] Fully **offline/local**: the launcher's own first-run demo-ingest uses
  a synthetic CSV fixture (no network); `lqe live`'s real-data path is
  unchanged (ccxt public + optional local Ollama, as before).
- **Tests:** ✅ `tests/unit/test_ops_jobs.py` (10 tests: JobManager
  ingest/backtest/live start-stop against an offline CSV fixture) ·
  `tests/integration/test_ui_jobs_routes.py` (7 tests: the HTTP surface via
  `TestClient`, including that control panels render only when
  `jobs_enabled` and are absent otherwise) · `tests/safety/
  test_onboarding_gate.py` (6 tests) · `tests/integration/
  test_run_launcher.py` (4 tests: `_seed_demo_csv`/`_first_run_setup`,
  including the fast-path when a catalog already exists) · full existing
  `lqe live` suite unchanged and green post-extraction · **verified live**
  against a real running server (not just TestClient): first-run auto-
  ingest completed, the Floor page rendered the control panel, a real HTTP
  `POST /api/jobs/live/start` (offline CSV adapter) brought up all 51
  models trading, and `POST /api/jobs/live/stop` cleanly halted it.
- **Exit gate:** ✅ full suite green (336 passed, 8 correctly skipped) +
  ruff + mypy + license gate green; `git tag m18-done`.

## M19 — Institutional UI/UX polish (Obsidian Desk, applied)  · L · Dep: M18  ✅ `m19-done`
**Goal:** it doesn't just work — it looks like a Goldman/Bloomberg-grade
instrument. Apply the design system to the *built* FastAPI + Jinja + WebSocket
UI. The `ui-ux-pro-max` engine independently recommended this exact profile
(Dark-OLED · dense dashboard · status colors · mono numerics), which
confirms the direction.

**Note on scope:** the Obsidian Desk tokens/typography/layout (status rail,
mode spine, tape, inspector) were already built to this exact spec back in
M7/M9/M10 — verified by diffing `theme/desk.css` against the color tokens
above, which matched byte-for-byte before this milestone touched anything.
M19's real remaining work, below, was the chart vendoring decision (owner
confirmed: vendor, don't hand-roll), the command palette, toasts, and a
genuine AA-contrast audit — not a rebuild.

**Design system (build to this):**
- **Direction:** "Obsidian Desk" — deep graphite, **one** amber heritage
  accent, **color only ever means something** (long / short / intelligence
  / risk). Full spec: `archive/28-ui-ux-design-system.md`.
- [x] **Color tokens (CSS custom properties):** `--void #07090D` · `--desk
  #0E131B` · `--slab #131A24` · `--ridge #1E2836` · `--ink #E9EEF5` ·
  `--mute #7A88A8` (lightened from the spec's literal `#6B7A90` — see AA
  contrast note below) · `--amber #F0A62A`; semantic `--long #35C08B`
  (bullish) · `--short #F0524D` (bearish) · `--intel #7C7BF2`. **AA
  contrast audit** (`tests/integration/test_ui_design_system.py`): computed
  WCAG contrast for every declared text color against every declared
  background straight from `desk.css`'s own `:root` block — found `--mute`
  at 4.01-4.27:1 on `--slab`/`--desk` (below the 4.5:1 this spec itself
  requires), fixed by lightening to `#7A88A8` (4.9-5.6:1, same hue). Never
  color-alone: badges/tags pair color with text; candlesticks pair
  bullish/bearish with fill-vs-outline (below), not hue alone.
- [x] **Typography:** unchanged from M7 — Inter/system-ui + JetBrains
  Mono/monospace, `font-variant-numeric: tabular-nums`. Extended
  `table.data td` (was missing explicit tabular-nums on all four data
  tables — Catalog/Research/Daily/Risk) to declare it explicitly rather
  than relying on the mono font's inherent fixed-width.
- [x] **Layout:** status rail / mode spine (`F1..F7`) / tape / inspector
  unchanged from M7-M10. Added the **`⌘K`/Ctrl+K command palette** (below)
  and a **Floor hero** (candlestick price + streaming equity, "top, large,
  high-contrast" per the hierarchy this spec calls for) — center-hero was
  the one layout element not yet built.
- [x] **Charts — vendored, not hand-rolled** (owner's explicit call):
  **TradingView Lightweight Charts v5.2.0** (Apache-2.0 → `ALLOW`,
  confirmed offline-vendorable — fetched once from the official npm
  distribution, hash-pinned, committed to `ui/theme/vendor/`, documented in
  `ui/theme/vendor/README.md` since the Python license gate can't see a
  vendored JS asset). New `StateReader.price_series()`/`.equity_curve()`
  read straight off existing `MarketEvent`/`RiskStateEvent` records — no
  new event type. New `GET /api/chart/price` (candlestick, bullish
  `#26A69A`/bearish `#EF5350`, **fill-vs-outline**: bullish is
  hollow/outline-only, bearish solid-filled, so the distinction survives
  colorblindness) and `GET /api/chart/equity` (streaming area, `--intel`
  fill) on Floor, with a **pause/resume** control, the current price/
  equity as **big KPIs**, an accessible **data-table fallback** (toggle
  button, real `<table>`, not decorative), and **downsample to ≤1000
  points** (evenly-strided, preserves first/last) so a long-running feed
  stays responsive.
- [x] **Motion 4/10:** 150-300ms `transition`s on buttons/cards/palette
  items/toasts; the existing blanket `prefers-reduced-motion: reduce` rule
  (M9) disables all of it — verified by a test that the rule's own block
  contains `transition`/`animation`/`none`/`!important`.
- [x] **A11y:** `:focus-visible` rings (amber outline) on every interactive
  element; sticky `table.data thead th` headers; tabular numerals on every
  data cell; no emoji-as-icon (verified: the project's existing ★/✓/✗/◇
  typographic glyphs are intentional "pair color with a glyph" markers, not
  emoji — a real emoji denylist scan of every template/script found none);
  chart data-table fallback (above).
- [x] **Tasks:** tokens were already CSS variables (M7); added toasts
  (`aria-live="polite"`, real feedback for KILL/AUTOPILOT/job actions
  instead of a blind reload-with-no-feedback), the command palette, sticky
  table headers, tabular-nums, focus rings, and the hero chart. Verdict
  chips/badges/KPI-style stats already existed (M7-M9) and needed no
  rework. Dark-only, unchanged. Empty-state handling: the hero chart panes
  show "No price/equity data yet." until the first real data arrives.
- [x] **Tests:** ✅ `tests/integration/test_ui_design_system.py` (10 tests:
  computed AA contrast for every token pair, focus-visible declared,
  reduced-motion disables transitions/animations, tabular-nums present,
  sticky headers present, no disallowed emoji, command palette + toast
  markup on every page, fill-vs-outline candlestick colors) ·
  `tests/unit/test_state_reader.py` (+11: `price_series`/`equity_curve`
  correctness, downsampling preserves first/last and is a no-op within
  budget) · `tests/integration/test_ui_chart_api.py` (7: the
  `/api/chart/*` HTTP contract, default-symbol resolution, empty-session
  behavior, vendored asset served with its license header intact) ·
  **verified live** against the real `lqe desk` server (not just
  TestClient) with the actual `runs/desk-preview/audit.jsonl` fixture:
  hero chart markup rendered, vendored library served (200), real
  candlestick/equity JSON flowed from `/api/chart/price`/`/api/chart/
  equity`, command palette markup present on every view, control panels
  correctly absent (jobs disabled on this read-only render path).
- **Exit gate:** ✅ full suite green (372 tests, 8 correctly skipped) +
  ruff + mypy + license gate green; `git tag m19-done`.

## M20 — Live Trade Blotter (the trade book you can watch)  · M · Dep: M19  ✅ `m20-done`
**Goal:** when a trade happens, you *see* it — unmistakably. (This is very
likely a display/plumbing gap, not a trading gap — the fix includes proving
trades actually flow.)

- [x] A first-class **Blotter** view (`/blotter`, `F8`) + the existing
  compact live **Tape** strip on the Floor (already shows fills generically
  since M7 -- unchanged). One row per fill, newest on top, live via
  WebSocket (`/ws`'s frame now carries `blotter` alongside `snapshot`/
  `tape`). Columns (mono, tabular): time · model · symbol · side (long/
  short color **+** glyph, ▲/▼) · qty · fill price · fee · slippage bps ·
  sim P/L. Filter by model/symbol/side (client-side, populated from the
  rendered rows so it can't drift).
- [x] Show the **full order lifecycle**, not just fills: intent → risk
  decision (**APPROVE / CLAMP / REJECT** + `rule_hits` + the signal's own
  `reason`) → fill/partial/reject. New `StateReader.blotter()` reconstructs
  this straight off `OrderIntent`/`RiskDecision`/`Order`/`FillEvent` already
  in the audit log (no new event type) -- one row per fill; a REJECTed (or
  approved-but-not-yet-filled) intent gets exactly one no-fill row, so
  nothing silently vanishes.
- [x] **Unmissable feedback:** a new fill flashes its Blotter row (CSS
  keyframe, `prefers-reduced-motion`-safe) + a toast (`aria-live`) + pulses
  the matching Floor model cell (`data-model` attribute added). Optional
  Web-Audio beep, **off by default**, toggle persisted to `localStorage`.
- [x] **Honest empty state:** new `blotter_empty_state_reason()` --
  deterministic, computed from the same snapshot the rest of the desk
  reads: "Warming up -- waiting for the first bars to arrive." (zero bars
  seen) / "Tracked book has 0 promoted models -- exploring in the
  sandbox." (bars flowing, nothing promoted) / "No signals in the last
  bars (models are watching)." Never a blank panel.
- [x] **Verified trades genuinely flow**
  (`tests/integration/test_live_blotter_flow.py`): runs the *real* live
  fleet (offline CSV adapter, a genuine up/down price cycle so momentum
  and mean-reversion models both have an honest reason to fire) and
  asserts real fills reach `DeskData.blotter()` -- this is the actual
  fleet-to-view path, not a synthetic fixture standing in for it. Passed
  on 4 separate runs (real wall-clock timing, not flaky).
- [x] **Reconciliation panel:** new `StateReader.reconciliation()` --
  net position + realized P&L + trade count per model, reusing the same
  FIFO lot accounting `model_cells()` already reads from (one source of
  truth, not a second computation that could diverge). Tied out to the
  audit log by construction, same as everything else this view reads.
- **Tests:** ✅ `tests/unit/test_state_reader.py` (+9: a hand-built audit
  log covering all three verdicts -- REJECT with no fill, CLAMP with a
  partial-then-final fill across two rows, APPROVE with one fill and its
  P&L delta; ordering; incremental `after_seq` polling; reconciliation
  matches position/P&L; all three empty-state branches) ·
  `tests/integration/test_ui_blotter.py` (9: the view renders, filters/
  sound-toggle/reconciliation-panel markup present, nav entry present,
  honest empty state renders when there are no trades, `/api/blotter`
  JSON contract + incremental polling, the WS frame carries blotter rows)
  · `tests/integration/test_live_blotter_flow.py` (1: the real-fleet
  fills-genuinely-flow test above) · `tests/honesty/test_ui_honesty.py`
  extended to cover `/blotter` (PAPER·LIVE LOCKED shield, no raw stdout,
  no profit-language) · `tests/safety/` (AST lockout scans) unchanged and
  green -- the Blotter constructs no `Order`, confirmed by the existing
  `make_order` lockout test with zero modification needed. **Verified
  live** against the real `lqe desk` server with `runs/desk-preview/
  audit.jsonl`: the Blotter page rendered real fills, the nav/`F8` link
  worked, `/api/blotter` returned real lifecycle JSON, and a real
  WebSocket connection's first frame carried 15 real blotter rows.
- **Exit gate:** ✅ full suite green (391 tests, 8 correctly skipped) +
  ruff + mypy + license gate green; `git tag m20-done`.

## M21 — The "Engine Room" conversation (watch the LLM, ML & autopilot talk)  · L · Dep: M19  ✅ `m21-done`
**Goal:** witness the LLM, the optimizer, the validator, and the autopilot
communicate — in plain English, live, no code or cryptic IDs. (Agent-UX
research: showing intermediate steps as inline "tool-call cards" kills the
black-box feeling; the interface is the *accountability layer* between
intent and autonomous action.)

**Scope note:** this feed is *added alongside* the existing Intel
decision-cards view (M9), on `/intel`, not a replacement for it — the
cards remain a useful per-hypothesis summary; the new feed is the
turn-by-turn "watch them talk" experience this milestone asks for. Both
read the same audit events honestly, from the same `StateReader`.

- [x] A **conversation/timeline feed** (new `StateReader.conversation()` /
  `ConversationMessage`/`ConversationPayload`) rendered as a readable
  dialogue between named participants: **Strategist** (`HypothesisEvent`)
  · **Optimizer** (`TrialEvent`s aggregated into one card per hypothesis —
  "Ran N trials — best Sharpe X (params)", never one message per trial) ·
  **Judge** (`ValidationEvent`) · **Autopilot** (`NarrationEvent`) ·
  **Risk** (`ControlEvent`/`DeRiskEvent`). Verified against a **real**
  autopilot campaign (offline CSV bundle, `lqe autopilot --steps 3
  --trials 5`): produced exactly this dialogue shape with real numbers
  ("Ran 5 trials — best Sharpe -27.68 (fast=10, slow=22)", "✗ FAIL — DSR
  0.05, PBO 0.00, doesn't survive costs; doesn't beat equal-weight").
- [x] **Color-coded by participant**, verdict-driven for the Judge:
  Strategist/Optimizer/Autopilot/Risk get fixed hues (`--intel`/`--mute`/
  `--amber`/`--short`); the Judge's card carries a `verdict` field so its
  color is long/short **by outcome**, not a fixed hue (tested: only Judge
  messages ever carry a verdict). **No code, no JSON, no cryptic IDs** in
  the default text (`hypo_id`/`candidate_id`/`trial_id` are internal
  grouping keys only, never rendered) — a native `<details><summary>
  Details</summary>` discloses the Judge's evidence dict as plain `k: v`
  lines, never raw JSON, for power users.
- [x] **Honesty is structural:** promotion messages are attributed to the
  **Judge**, not the Strategist or Autopilot ("the Judge is visibly the
  one who decides") — tested explicitly. The existing honesty banner/
  shield is unchanged.
- [x] **Works without the LLM:** `conversation()` reads `NarrationEvent
  .text` as-is, regardless of which narrator (RuleBased or Ollama) wrote
  it — no LLM-specific branch exists, so the feed is identical whether or
  not Ollama is running.
- [x] **Accountability + control:** the status rail (KILL + AUTOPILOT
  toggle) renders on every page via `base.html`, Intel included — no new
  code needed, just confirmed and tested. Kill and de-risk events appear
  as their own **Risk**-attributed messages in the feed.
- [x] **Source + replay:** new `GET /api/conversation?at_seq=` mirrors
  `/api/graph`'s exact deterministic-replay pattern; a new `#convo-
  scrubber` timeline control (same UX as the Engine 3D view's scrubber)
  replays the conversation exactly as it was at any past `seq` — verified
  live that scrubbing to `at_seq=5` mid-campaign correctly showed a
  partial "4 trials" Optimizer summary instead of the final "5 trials".
- **Tests:** ✅ `tests/unit/test_state_reader.py` (+10: a hand-built full-
  loop audit log covering every participant + trial-aggregation-picks-
  the-best-not-each-one + Judge-only-carries-verdict + kill/de-risk-as-
  messages + promotion-attributed-to-Judge + deterministic at_seq replay
  + no-JSON/no-cryptic-IDs + templated-narration-without-LLM + empty-log
  handling) · `tests/integration/test_ui_conversation.py` (8: the feed +
  scrubber render, the empty state, the existing cards section is
  untouched, the `/api/conversation` contract + `at_seq` replay, pause/
  kill reachable) · `tests/honesty/test_ui_honesty.py` extended to cover
  `/intel` (was an existing gap since M9, closed here) · full existing
  `tests/safety/`+`tests/honesty/` suites unchanged and green. **Verified
  live** against a real `lqe autopilot` campaign (not a synthetic
  fixture): ingested + built a real replay bundle, ran 3 real hypothesis
  cycles, served the resulting audit log via `lqe desk`, and confirmed
  the rendered feed, the scrubber's deterministic mid-campaign replay,
  and the kill control all worked end to end.
- **Exit gate:** ✅ full suite green (409 tests, 8 correctly skipped) +
  ruff + mypy + license gate green; `git tag m21-done`.

## M22 — v3 hardening, review & tag  · M · Dep: all
- [ ] Extend `tests/safety` + `tests/honesty` to the new surfaces
  (launcher, blotter, conversation): no `Order` path, no CLI/stdout
  rendered, honesty labels present, kill reachable, `127.0.0.1` only.
- [ ] Re-run the full safety/honesty review **with evidence** →
  `V3-RELEASE-REVIEW.md`.
- [ ] Regenerate `THIRD_PARTY_NOTICES`; if TradingView Lightweight Charts
  was vendored, confirm the license gate passes it (Apache-2.0 = ALLOW
  under the tiered/transitive/fail-closed policy in `docs/11` §11.11).
- [ ] Update `README` / `USER-GUIDE` / `COMPONENT-GUIDE`; tag **v3.0**.
- **Exit gate:** all gates green with evidence; the product launches with
  one click, shows trades you can watch, looks institutional, and lets you
  witness the engine-room conversation — with every non-negotiable intact.
  `git tag v3.0`.

---

## Sequencing, scope & notes
- **Order:** M18 (launch) → M19 (design foundation) → **M20 (blotter) + M21
  (conversation)** built in the polished system → M22 (review).
- **Scope discipline:** additive UX/visibility only. Do not touch the
  safety core; do not add anything from `GUARDRAILS.md`'s "OUT OF SCOPE"
  list. The M22 review must prove the 9 non-negotiables are intact.
- **Not in v3** (deferred to v4/later — see [`14-v4-catalog-expansion.md`](14-v4-catalog-expansion.md)
  and the v2 §5/§7 open threads): extending resume to cover
  autonomy/promotion history, standing up a real remote CI runner, and
  widening the autopilot search surface toward the full catalog. These are
  orthogonal to the four UX asks here.
- **Model tip for the builder:** M19 (design system) and M21
  (agent-conversation reasoning) reward Opus; M18 and M20 are mechanical →
  Sonnet.

## Sources
`ui-ux-pro-max` design skill (Dark-OLED + dense-dashboard + status-color
recommendation; chart guidance) · `frontend-design` skill (distinctive
committed direction) · [Trading App Design 2026 — Lollypop](https://lollypop.design/blog/2026/june/trading-app-design/)
· [IBKR blotter interface](https://www.ibkrguides.com/traderworkstation/understand-blotter-interface.htm)
· [Agent UX 2026 — Fuselab](https://fuselabcreative.com/ui-design-for-ai-agents/)
· [UI frameworks for AI agents 2026 — Fast.io](https://fast.io/resources/best-ui-frameworks-ai-agents/)
· TradingView Lightweight Charts (Apache-2.0).
