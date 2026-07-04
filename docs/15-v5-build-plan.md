# PRAXIS Quant — V5 Build Plan (developer-ready)

*2026-07-04 · the single doc the dev team builds V5 from. Merges the UI/UX audit fixes (`UI-UX-AUDIT.md`) and the V5 roadmap (`PRAXIS-QUANT-V5-BLUEPRINT.md`) into one interleaved, step-by-step plan. Place at `docs/15-v5-build-plan.md`.*

## What V5 is (one line)
Rename `lightweight-quant-engine` → **PRAXIS Quant**, expand to a **multi-instrument universe** (which wakes the dormant cross-sectional/lead-lag/pairs/regime sleeves), add three **value-beyond-P&L** pillars (Insight · Skill · Proof), and make the whole thing **fabulous** — all additive, no safety change.

## How to use this doc
- One milestone per focused session, in order. Don't start the next until the **exit gate** is green; `git tag mN-done` at each.
- Every milestone carries the **merged Definition of Done** (§DoD) — engine gates **and** the design/a11y quality bar.
- Tests-first for anything touching `risk/`, `execution/`, `autonomy/`, the promotion gate, or a safety/honesty surface.
- **Model tier:** Opus for the universe core (M27), the gate/determinism work, and the signature interactions (M29/M32); Sonnet for the rest.

## Non-negotiables (unchanged — re-proven at M35)
Paper-only lockout · one `make_order` after the (now cross-instrument) risk gate · promotion gate un-bypassable, **trial-count spans models × instruments** · full audit + determinism · GUI renders no CLI/stdout · localhost only · runtime deps permissive (tiered/transitive/fail-closed license gate) · no profitability claims. Full list: `GUARDRAILS.md`.

## Two NEW standing gates for V5 (every milestone)
1. **Cross-instrument determinism:** synchronized multi-symbol replay reproduces the book bit-for-bit; a late/missing symbol ⇒ no-trade + logged, never a desync.
2. **Performance-intact:** the value layers (Insight/Skill/Proof) are **read-only over the audit log**. A test asserts no value module imports the engine hot path. (Your constraint: value must not degrade performance.)

## The honesty rail for value features (hold the line)
Insight = **descriptive, not predictive** (correlation ≠ causation; regimes are observations). Skill scores **process, not outcome**. Proof proves **what was validated, not that it profits**. Every new surface keeps the `SIMULATED · not evidence of edge` label. Delight (the Promotion Moment etc.) celebrates *passing validation*, never *making money*.

---

## Design quick-reference (so UI work starts immediately)
All in `src/lqe/ui/theme/desk.css` unless noted. These are the audit's concrete fixes.

**Type scale — the highest-ROI fix (audit §1).** Bump the floor:
```css
:root { /* body */ }  body { font-size:14px; }        /* was 13 */
.stat .k,.mode,.foot,.kv .k { font-size:11px; }        /* label floor was 9–10 */
.tag-unproven,.tag-validated,.badge { font-size:10px; }/* was 8.5–9 */
```
**Press feedback on every control (audit §2):**
```css
.kill,.autopilot,.ctl-btn,.mode { transition:transform .12s ease-out, background-color .18s ease-out, color .18s; }
.kill:active,.autopilot:active,.ctl-btn:active { transform:scale(.97); }
```
**Tune the flash / motion (audit §7):** `@keyframes blotter-flash` duration `1.1s → .7s`; add list stagger 30–50ms on grid/tape load-in; signature moments use spring-ish easing, exit ~65% of enter.
**Tokens (keep — already good):** `--void#07090D --desk#0E131B --slab#131A24 --ridge#1E2836 --ink#E9EEF5 --mute#7A88A8 --amber#F0A62A --long#35C08B --short#F0524D --intel#7C7BF2`. Fonts Inter + JetBrains Mono, tabular-nums on all numbers. **Preserve** focus-visible rings, global `prefers-reduced-motion`, aria-live toasts, chart data-table fallback.
**Tokenize inline headings:** replace repeated `<h2 style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--intel)">` with a `.section-h` class.
**Icons:** vendor one SVG set (Lucide) into `theme/vendor/`; give `.mode` spine items icon + label; retire the ad-hoc `◇`/entity glyphs.

---

## Milestones (M26 → M35) — feature + UI interleaved

### M26 · Desk Polish Foundation  · S–M · Opus-optional · Dep: v4
*Make the current product fabulous before adding scope. (Audit P0 + the two small signature controls.)*
- [ ] Type-scale bump (base 14 / labels 11 / tags 10); tokenize inline `<h2>` → `.section-h`.
- [ ] Press-feedback (`:active scale(.97)`) on `.kill/.autopilot/.ctl-btn/.mode`.
- [ ] **Restore living model cells** (audit §4): re-add the stance bar + 24-bar sparkline + `--intel` left-edge tint to `templates/floor.html` cells (they regressed to text-only vs the mockup). Fire = amber pulse (infra exists).
- [ ] Nav icons (Lucide, vendored) on the spine; `blotter-flash` → .7s; stagger grid/tape reveal.
- [ ] **Weighty KILL** (brief hold/confirm → decisive red state → feed dot red, cells→halted → calm "Stopped. Nothing is running.") and **power-on AUTOPILOT** (the existing `.autopilot.on` intel glow blooms; toast "Autopilot engaged — I'll research and validate; take the wheel anytime").
- [ ] Control-panel `<select>`/inputs get visible `<label for>`; "Start Live" shows spinner + disabled during spin-up.
- **Tests:** AA contrast on new sizes; reduced-motion still kills all animation; focus rings intact; no emoji-as-icon; no CLI/stdout; honesty labels present; UI constructs no `Order`.
- **Gate:** the desk looks and *feels* polished on the current single-instrument build. `tag m26-done`.

### M27 · Universe Core (multi-instrument)  · L · Opus · Dep: M26 — DONE, tag `m27-done`
*Approach A from the blueprint: one deterministic loop, a fan-out `Universe`.*
- [x] `Universe` object: synchronized multi-symbol bar stream (5 spot majors: BTC, ETH, SOL, BNB, XRP); deterministic bar-alignment (late/missing symbol ⇒ no-trade+logged). `core/universe.py`.
- [x] Models declare consumed instruments; single-instrument models run per-symbol; the loop passes cross-sectional models the whole universe slice. `backtest/universe_runner.py::run_universe_backtest` (one `Session` per instrument, sharing one `Engine`); `catalog_scale.py`'s `DEFAULT_UNIVERSE` replaces the fake synthetic universe those adapters were permanently inert against.
- [x] **Unified cross-instrument risk** (per-instrument limits + portfolio gross/concentration/per-sleeve budgets) + **one reconciliation** tying every instrument to the single audit. `risk/portfolio_context.py` + 2 new rules (`check_portfolio_gross_exposure`, `check_sleeve_concentration`) in `risk/rules.py`; `StateReader.reconciliation()` now keyed by `(model, symbol)`.
- [x] **Gate trial-count spans models × instruments** (the honest-N grows → promotion bar rises). No gate code change needed — `ExperimentRegistry.trial_count()` was already a blind `count(*)` (same finding as M23's own audit); it grows automatically once the catalog has (model, symbol) pairs to search.
- [x] UI: status rail shows the universe + per-symbol feed health. `base.html`'s hardcoded `data_health[0]` → loops the full list (the data's been list-shaped since before M27).
- **Tests:** multi-symbol replay deterministic; bar-misalignment handled; portfolio risk caps hold across instruments; reconciliation ties to audit; gate N includes instruments. All shipped — see `HANDOFF.md` §1j.
- **Gate:** 5 spot symbols run as one deterministic, reconciled, gated book — proven via `run_universe_backtest` (backtest side). `tag m27-done`.
- **Live-loop follow-up (done, same session as the sanity check that precedes M28 — see `HANDOFF.md` §1k):** `live/session.py`/`live/multi_model_runner.py` rewired to N symbols — `LiveSession` now builds one `LiveMultiModelRunner` per symbol sharing one `Engine`/kill switch/`PortfolioContext`, driven by `Universe.cycles()`; `cli.py`/`ops/jobs.py`/`ui/app.py`+`desk.js` updated `--symbol`→`--symbols`(`s`). Found and fixed two real latent bugs along the way (both pre-existing, only surfaced by a genuinely small/asymmetric universe): `catalog_scale.py`'s stat-arb entries crashed on a <2-sibling universe (now a quarantine-free no-op), and `_synthetic_allocator_closes` silently collapsed to a 2-asset dict when `symbol == "ETH-USDT"` (key collision), reproducing skfolio's known HRP 2-asset crash.

### M28 · Wake the Sleeves  · M · Dep: M27 — DONE, tag `m28-done`
- [x] Turn on cross-sectional momentum/reversal/low-vol ranking, BTC→alt lead-lag, cointegration pairs (ETH/BTC, SOL/ETH…) — already admitted since M23/M24, proved firing together across the real universe (not just one illustrative model each) via a new full-catalog test + a fixed `scripts/diversification_report.py` (previously silently starved 2 of 5 real symbols from ever reaching those adapters). **"Universe-regime" did not exist in the codebase before this milestone** — built a new native `UniverseRegimeGateAdapter` (correlation-gated systemic/idiosyncratic regime switch), catalog 104→106. Each passes intake + the universe-scaled gate.
- [x] UI: Floor becomes **models × instruments** using the M26 living cells; show family · sleeve · instrument. `StateReader.model_cells()` rewritten to yield one cell per (model_id, symbol) pair; verified live (same model_id renders as 5 independent cells with 5 different real trade counts).
- **Tests:** each dormant adapter produces real, gated signals across the universe; diversification score now has cross-instrument return streams to measure. Done — see `HANDOFF.md` §1l.
- **Gate:** the previously-dormant intelligence is alive and honestly gated. `tag m28-done`.

### M29 · Universe UI + ⭐ The Promotion Moment (signature)  · M · Opus · Dep: M28
*The signature moment lands here — gate + universe are both live.*
- [ ] Neural web spans the universe; diversification score shown across instruments; **3-tier visual hierarchy + whitespace pass** (audit §5 — the added density needs it: hero number / section / detail).
- [ ] **The Promotion Moment:** when a candidate passes the gate, animate it **crossing from the dim sandbox into the bright validated core** (shared-element on the neural web), a gold ring pulse, a line "Validated out-of-sample — promoted to the tracked book (DSR x.x, PBO x.x)", optional tone. Honest label inline. Spring easing; reduced-motion → instant state.
- **Tests:** promotion animation fires only on a real gate PASS; carries the honesty label; reduced-motion safe; still read-only.
- **Gate:** the product's most meaningful event is *earned and memorable*. `tag m29-done`.

### M30 · Perps & Carry  · M · Dep: M27
- [ ] Perp/funding data adapter (validated like all data); wake the **carry/basis** sleeve (funding-rate carry, cash-and-carry basis) — structurally uncorrelated diversifiers.
- **Tests:** funding data validated; carry/basis measurably low-correlation to directional sleeves.
- **Gate:** the crown-jewel diversifiers are live. `tag m30-done`.

### M31 · Market Map — Insight pillar (flagship value)  · L · Dep: M28
- [ ] Read-only **Market Map**: cross-instrument correlation clusters + universe regime state + lead-lag flows, built over the audit + universe data. Charts get direct-labels + subtle gridlines (audit §10).
- **Tests:** **performance-intact** (Market Map imports no engine hot path); descriptive-only honesty labels present.
- **Gate:** the operator can *see and understand what the market is doing*. `tag m31-done`.

### M32 · Market Narrator + Engine-Room Hero (signature)  · M · Opus · Dep: M31
- [ ] **Market Narrator:** LLM (or templated fallback) plain-English market-structure narration in the `--intel` channel — honest, descriptive, no profit implication.
- [ ] **Engine-Room cinematic hero** (audit §4): elevate the conversation feed — participant marks, gentle typewriter reveal on the newest line (reduced-motion safe), the **Judge verdict landing with weight** (decisive green/red ruling).
- **Tests:** narrator emits text only, never a size/order; works with LLM absent; feed deterministic on replay; no code/JSON in default view.
- **Gate:** watching the AI think is a front-door, cinematic experience. `tag m32-done`.

### M33 · Research Journal + Process Score — Skill pillar  · M · Dep: M28
- [ ] From the audit log: a **Research Journal** (every hypothesis, yours or the autopilot's), a **process-quality score** (pre-registered? trials counted? survived OOS? — *process, not outcome*), and "why it failed" coaching.
- **Tests:** performance-intact (read-only); scoring rewards process not P&L; honest labels.
- **Gate:** the product makes the operator a sharper researcher. `tag m33-done`.

### M34 · Proof-of-Research  · M · Dep: M33
- [ ] Export a **signed, replayable, verifiable research record** (what was tried + validated), reconstructable byte-for-byte from the audit.
- **Tests:** an exported record replays byte-identical and re-verifies its validation; performance-intact.
- **Gate:** research others can trust. `tag m34-done`.

### M35 · First-run, P2 polish, PRAXIS rename & Release  · L · Dep: all
- [ ] **First-run story** (audit §4): replace the bare spinner with one screen — "Three things happen here: models trade live (simulated) · an AI proposes experiments · a math judge decides what's real" → button "Watch it work" → land on the Floor with a soft guided highlight of KILL + AUTOPILOT.
- [ ] P2 polish: graceful narrow-width reflow of the desk grid; a **reliable keyboard layer** (re-introduce hotkey nav carefully — the palette was removed for a bug); unify one SVG icon system; final stagger/easing pass; virtualize blotter/tape if long.
- [ ] **PRAXIS Quant rename** touch-points: package (`praxis` with an `lqe` compat shim), UI brand "PRAXIS Desk", `run.bat`/CLI (`praxis`), docs, `THIRD_PARTY_NOTICES`.
- [ ] Full review with evidence → `V5-RELEASE-REVIEW.md`: safety + honesty + **performance-intact** + **cross-instrument determinism** + the design/a11y quality bar. Regenerate notices. **`tag v5.0`.**

---

## Merged Definition of Done (every milestone)
**Engine:** ruff + mypy clean · unit + property + parity + safety + honesty tests green · audit hash-chain verifies · cross-instrument replay deterministic · promotion gate un-bypassable (N spans instruments) · **performance-intact** (value modules read-only) · license gate green · no `Order` outside `make_order`.
**Design/UX quality bar (new for V5):** AA contrast (incl. the new type sizes) · visible focus rings · `prefers-reduced-motion` honored on every new animation · tabular numerals on all numbers · **no CLI/stdout rendered** · honesty label on every new Insight/Skill/Proof/celebration surface · SVG icons only (no emoji) · press-feedback on interactive controls · body type ≥ 14px / labels ≥ 11px.

## Decisions made for you (redirect any — the choice tool dropped last turn)
Universe = **5 spot majors (M27) → +perps (M30)**; broad/cross-asset = v6. Value pillars = **Insight (flagship) + Skill + Proof**; community/competition = v6 (needs multi-user). Scope = **flagship-focused, staged**. Change any and the milestone spine holds.

## Kickoff prompt (paste into Claude Code to start M26)
```
You are building PRAXIS Quant V5 from docs/15-v5-build-plan.md. Read CLAUDE.md, GUARDRAILS.md,
WORKFLOW.md, docs/15, and the design quick-reference in docs/15 first. IGNORE docs/archive/.
V5 is additive — never weaken a safety non-negotiable; every milestone re-proves them, plus the two
new standing gates (cross-instrument determinism, performance-intact) and the design/UX quality bar.
Build strictly by milestone, in order, one at a time, tests-first for safety/honesty surfaces.
STEP 1 — before any code, reply with: (a) confirmation you can read desk.css + the templates,
(b) your M26 task list and exit gate from docs/15, (c) the tests you'll write, (d) any ambiguity.
Wait for my "go". STEP 2 — on "go", implement M26 (Desk Polish Foundation) only, meet its exit gate,
`git tag m26-done`, and STOP for review. Do not exceed M26. Honesty labels stay on every surface;
delight never implies profit.
```

## Sources
`UI-UX-AUDIT.md` · `PRAXIS-QUANT-V5-BLUEPRINT.md` · `ui-ux-pro-max`/`frontend-design`/`brainstorming` skills · [micro-interactions 2026](https://primotech.com/ui-ux-evolution-2026-why-micro-interactions-and-motion-matter-more-than-ever/) · [emotional design — IxDF](https://ixdf.org/literature/topics/emotional-design) · [multi-asset architecture](https://traderevolution.com/learn/multi-asset-brokerage-platform/) · [reproducibility & decision-quality](https://arxiv.org/html/2504.18600v1).
