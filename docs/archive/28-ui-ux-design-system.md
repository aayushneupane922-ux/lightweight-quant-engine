# 28 — Obsidian Desk UI/UX Design System

The full design-token reference for the two-surface `localhost` app (docs/05
§5.1 is the one-paragraph recap of this file). Source of truth: the three
mockups that actually implement this palette —
[`obsidian-desk-model-floor.html`](../../mockups/obsidian-desk-model-floor.html)
(terminal), [`neural-engine-3d.html`](../../mockups/neural-engine-3d.html) and
[`neural-engine-2d.html`](../../mockups/neural-engine-2d.html) (the 3D/2D
neural-web + its no-WebGL fallback). Every token, size, and pattern below is
extracted from those three files, not invented — if the mockup and this doc
ever disagree, the mockup wins and this doc is stale.

> **Note on the other three mockups.** `neural-engine-holo.html`,
> `neural-engine-observatory.html`, and `neural-engine-plasma.html` are
> rejected mood-board explorations (cyan/magenta, gold/cyan, and brighter-amber
> palettes respectively). No spec doc links to them, and they don't share the
> `--void/--desk/--amber/--long/--short/--intel` token names. They're kept in
> `mockups/` as design-exploration history only — **do not build from them.**

## 28.1 Design principles (why the system looks like this)

1. **Honest telemetry, not a fake brain.** Every visual signal must trace to
   real audit-log state (docs/06 §6.5). Nothing is decorative filler except
   the starfield in the 3D scene (explicitly there so the scene "never looks
   empty" — a mood detail, not a data channel).
2. **Color means exactly one thing, always.** `--long`/`--short` are P&L and
   direction, full stop. `--intel` is the ML/LLM channel — used nowhere else,
   so intelligence/narration never masquerades as performance. `--amber` is
   the one heritage accent (brand, kill-adjacent warnings, the paper-lock
   shield) — restrained, not a rainbow.
3. **No CLI/stdout anywhere.** Every state a log line would carry is a
   designed component: progress → phase strip, results → tables/KPIs/charts,
   events → the **Tape** (§28.7), errors → an inline designed state.
4. **Dense but legible.** Institution-grade information density (13px base,
   tabular mono numerics) without becoming unreadable — hairline structure
   (1px borders) does the separating, not heavy chrome.
5. **WCAG AA, keyboard-first, motion-respectful.** Concrete gates in §28.9.

## 28.2 Color tokens

```css
:root {
  /* surfaces (dark → light) */
  --void:  #07090D;   /* page background */
  --desk:  #0E131B;   /* panel background (spine, inspector, 3D HUD cards) */
  --slab:  #131A24;   /* raised surface (status rail, cells, tape) */
  --ridge: #1E2836;   /* hairline borders/dividers */

  /* text */
  --ink:  #E9EEF5;    /* primary text/numerics */
  --mute: #6B7A90;    /* secondary/tertiary text, labels, timestamps */

  /* the one heritage accent */
  --amber: #F0A62A;   /* brand, kill-adjacent warnings, paper-lock shield, FIRED state */

  /* semantic (mean exactly one thing each, everywhere) */
  --long:  #35C08B;   /* long / positive P&L */
  --short: #F0524D;   /* short / negative P&L / halt / danger */
  --intel: #7C7BF2;   /* the ML/LLM channel — narration, meta-layer, conviction, promotion */
}
```

**Measured contrast** (WCAG relative-luminance formula, computed against the
three surface tokens):

| Foreground | on `--void` | on `--desk` | on `--slab` | AA (normal text, 4.5:1) |
|---|---|---|---|---|
| `--ink` | 17.1:1 | 16.0:1 | 15.0:1 | ✅ (AAA) |
| `--mute` | 4.6:1 | 4.3:1 | 4.0:1 | ⚠️ borderline — see rule below |
| `--amber` | 9.7:1 | — | 8.5:1 | ✅ |
| `--long` | 8.6:1 | — | 7.6:1 | ✅ |
| `--short` | 5.7:1 | — | 5.0:1 | ✅ |
| `--intel` | 5.7:1 | — | 5.0:1 | ✅ |
| `--ridge` (structural border) | — | — | 1.2:1 | N/A — structure only, never conveys state alone |

**Token usage rules (derived from the numbers above, not guessed):**
- `--mute` clears AA only on `--void`, and only barely on `--slab`/`--desk`.
  **Never use `--mute` for a value someone needs to read correctly** (P&L,
  quantities, verdicts) — only for secondary labels (`.k` keys, timestamps,
  family tags) that are redundant with an adjacent `--ink`/semantic-colored
  value. This matches actual mockup usage: every `--mute` text in
  `obsidian-desk-model-floor.html` sits next to a colored/`--ink` value that
  carries the real information.
- `--ridge` borders are structural only (1.2:1 — well below the 3:1 non-text
  contrast minimum). State is never conveyed by a border alone; every
  stateful border in the mockups is paired with a text label (badges carry
  both a color **and** the word `LONG`/`SHORT`/`FIRED`/`HALTED`) — keep it
  that way (also satisfies §28.9's "not color alone" rule).
- `--amber`/`--long`/`--short`/`--intel` all clear AA on both `--void` and
  `--slab` — safe for small badge/label text, not just large text.

## 28.3 Typography

```css
:root {
  --ui:   "Inter", system-ui, sans-serif;         /* weights used: 400, 500, 600 */
  --data: "JetBrains Mono", ui-monospace, monospace;  /* weights used: 400, 500, 700 */
}
body { font-size: 13px; -webkit-font-smoothing: antialiased; }
.mono { font-family: var(--data); font-variant-numeric: tabular-nums; }
```

- **Inter** — all UI chrome: labels, headings, narration prose, buttons.
- **JetBrains Mono** — every number and every audit-adjacent identifier
  (P&L, timestamps, the Tape, table cells, badges) with `tabular-nums` so
  columns of numbers stay aligned as they tick.
- **Size scale observed in the mockups:** 9–9.5px (micro-labels: `.k` keys,
  `.fam` tags, badge captions), 10–11.5px (body/data rows, tape, tooltips),
  12–13px (base body, cell names), 14–15px (KPI values, section headings).
  Don't introduce sizes outside this scale — the density is the point.
- **Letter-spacing:** micro-labels and badges use `0.05em`–`0.16em` tracking
  (uppercase, small caps feel); body prose uses default tracking.

## 28.4 Spacing, radius & layout

- **App shell:** `grid-template-rows: auto 1fr auto` (status rail / body /
  tape). Body: `grid-template-columns: 64px 1fr 320px` (mode spine / main
  view / inspector).
- **Radius scale:** `3px` (badges, buttons, shield), `4–5px` (cards, narration
  panel), `6px` (3D HUD floating cards), `10px` (pill counters).
- **Border width:** `1px` hairlines everywhere (`--ridge`); `2px` only for an
  emphasis/accent edge (e.g. the `--intel` left-border on narration cards, the
  active mode-spine indicator).
- **Grid density:** the Model Floor uses
  `grid-template-columns: repeat(auto-fill, minmax(228px, 1fr))` with a
  `10px` gap — cards reflow, never horizontally scroll.
- **Card padding:** `12px 12px 11px` (floor cells), `14px` (inspector,
  floor container), `9px 16px` (status rail).

## 28.5 Navigation & chrome

- **Status rail** (top, `--slab` background): brand mark (`OBSIDIAN` +
  amber-bold `DESK`), live feed dot + exchange/symbol, UTC clock (mono),
  session KPIs (sim P/L, exposure, drawdown — `.pos`/`.neg` color the
  numbers), the **`PAPER · LIVE LOCKED`** amber shield (always visible, never
  removable), and the **KILL** button (outlined `--short`, fills on hover —
  never the primary/filled button style, so it never looks like a casual
  action).
- **Mode spine** (left, 64px, `--desk` background): `F1..F6` — **Floor ·
  Catalog · Research · Intelligence · Engine (3D) · Risk** (docs/05 §5.2/5.6).
  Active mode: `--amber` text + left border + a faint amber wash
  (`rgba(240,166,42,.06)`); inactive: `--mute`, hover brightens to `--ink`.
  Each item shows its function key in tiny mono type.
- **Inspector** (right, 320px, `--desk` background): the drill-in / narration
  panel — always the `--intel`-accented column, so "this is the
  intelligence layer talking" is spatially consistent everywhere it appears.
- **Autopilot / Kill in the 3D HUD:** an outlined amber pill (`◉ AUTOPILOT
  ON`) and the same paper-lock shield float over the 3D canvas — the
  non-negotiable controls follow you into every view, they don't live only on
  the 2D desk.

## 28.6 Model Floor cell anatomy

Each instrument cell (`.cell`) is a `--slab` card with a left accent bar
whose opacity encodes the meta-layer's conviction (`--intel`, at `.95/.5/.16`
opacity for hi/med/lo attention) — the one place conviction is shown as a
raw visual intensity rather than a number, and it's always paired with the
narration text in the inspector.

- **Header row:** model name + a small glyph (unique per family, e.g. `╱`
  breakout, `∿` MA-cross, `↗`/`↘` momentum, `≈` mean-reversion, `⊞`/`⋔`
  portfolio) + family tag (`--mute`, uppercase, tracked) on the left; a
  **state badge** on the right.
- **State badges** (`--data` font, bold, tracked letter-spacing): `ARMED`
  (`--mute` outline — idle/watching), `LONG`/`SHORT` (semantic color, filled
  8% wash + 45%-alpha border), `FIRED ▲`/`FIRED ▼` (`--amber` — just
  transitioned), `HALTED` (`--short` — risk breach, stopped).
- **Stance bar:** a 4px `--ridge` track with a centered tick and a colored
  fill bar showing current directional lean (long fills right of center,
  short fills left) — a glance-only micro-visualization, never the sole
  source of a number.
- **Row:** sim return (mono, `.pos`/`.neg`) + a tiny inline sparkline (SVG
  polyline, stroked in `--long`/`--short`/`--mute` matching the trend).
- **Footer (the honesty line, mandatory on every cell):** sample size +
  duration/status on the left (`n=41 trades · 3.2h`, or `insufficient data
  (n=6)` when too small to mean anything), and a **verdict** on the right —
  one of the four verdict states in §28.8. This footer is what stops a green
  sparkline from reading as "proven"; it never gets removed to save space.

## 28.7 The Tape (structured event feed — the CLI replacement)

A fixed-height (`118px`) scrolling strip at the bottom of the desk. Each row
is a CSS grid (`88px 92px 150px 1fr auto`): mono timestamp → a small colored
**action pill** (`FIRE`/`FILL`/`HALT`, styled like the state badges above) →
model name (`--ink`) → detail (`--mute`) → a mono trailing note (fee/slippage
/ risk verdict). The header carries an explicit **`structured · not a
console`** pill so the honesty claim is visible, not just true in code. A UI
test must assert this view never renders a raw stdout/log string (docs/05
§5.3) — the Tape is the only place a "log-like" feed is allowed, and even it
is fully structured, filterable rows, not text.

## 28.8 Honesty layer (mandatory everywhere, not just the 3D view)

- **The `SIMULATED` tag** — `--intel`-tinted banner
  (`rgba(124,123,242,.07)` background, `28%`-alpha border, `#b9b6f7` text),
  always visible on any live/intel surface, stating plainly that live
  performance is not evidence of edge and naming the sample-size caveat.
- **Verdict taxonomy** (used in the cell footer, the Tape, and the 3D HUD
  honesty strip — exactly these four, don't invent a fifth):
  - `observing` (`--mute`) — too early to say anything.
  - `⚠ survives` (`--amber`) — clears costs/plausible but not yet gated.
  - `❌ no edge (costs)` (`--short`) — a real, honest kill, shown as
    prominently as a win.
  - `★ validated` (`--long`) — passed the `PromotionGate` (docs/04); the
    **only** verdict that may ever imply "this is real."
- **`unproven` tag** — small `--mute`-outlined pill, mono font, for anything
  in the catalog that hasn't cleared intake/gate yet (docs/03 §3.4). Never
  hide this tag to make the catalog look more finished than it is.
- **Sandbox vs. tracked regions** (3D view): visually distinct — a dim,
  churning exploratory swarm (`--mute`/desaturated) vs. a bright validated
  core, each carrying its own persistent label
  (`Sandbox — exploratory · unvalidated` / `Tracked book — validated
  out-of-sample`). A promotion event is the **only** thing that visibly
  crosses from one region to the other (an amber pulse tracing sandbox →
  tracked), making the discipline itself visible, not just the churn.

## 28.9 Accessibility & motion contract

- **WCAG AA:** hold to the measured ratios in §28.2; when introducing a new
  foreground/background pairing, compute it (don't eyeball it) before
  shipping.
- **Not color alone:** every stateful indicator pairs color with a text label
  or icon (badges show both a hue *and* the word `LONG`/`HALTED`/etc.;
  verdicts show both a hue and a glyph `⚠`/`❌`/`★`). No cell, edge, or row
  may communicate state through color/opacity alone.
- **Keyboard-first:** the mode spine is reachable via `F1..F6`; a `⌘K`
  command palette reaches everything else; every interactive element needs a
  visible focus ring (a `2px` outline in `--intel` is the recommended token —
  it's reserved from the semantic colors and reads clearly against every
  surface token per §28.2's numbers). No mockup currently renders a focus
  state — implementers must add one; this is a known gap, not a deferred
  requirement.
- **`prefers-reduced-motion`:** the 3D scene must fall back to a calm static
  layout (no pulse/rotation animation); the 2D floor is unaffected since it
  has no continuous motion by default. `neural-engine-2d.html` (no WebGL, no
  animation loop) is also the designated fallback when WebGL itself is
  unavailable — both fallbacks already exist as mockups, wire both.
- **Update throttling:** live views poll/update at 1–2 Hz (never faster) —
  a performance requirement (docs/11 §11.11) that doubles as an honesty
  requirement: nothing should look faster/twitchier than the real decision
  cadence.

## 28.10 Implementation notes (FastAPI + NiceGUI)

- Ship the tokens in §28.2–28.4 as real CSS custom properties on `:root`
  (exactly as written above) so NiceGUI components, the Tape, and the 3D
  HUD overlay all read the same source of truth — don't fork the palette
  per-view.
- Self-host **Inter** and **JetBrains Mono** (the mockups pull from Google
  Fonts via `<link>`, which is fine for a mockup but is an outbound network
  call the shipped app shouldn't make — bundle the woff2 files locally so the
  app stays `127.0.0.1`-only with zero external requests, matching docs/11
  §11.11's "no outbound except ccxt public + optional local Ollama").
- The 3D HUD (`neural-engine-3d.html`) overlays plain HTML/CSS on top of a
  WebGL canvas rather than drawing UI text into the 3D scene — keep that
  split; it's why the HUD can reuse every 2D token/component unchanged.

## 28.11 Acceptance criteria

- Every color in the shipped app resolves to a `:root` custom property from
  §28.2 — no new hard-coded hex outside this token set.
  - Any addition to the palette ships with a measured contrast ratio, not an
  eyeballed one.
- Model Floor cells, the Tape, and the 3D HUD each carry their mandatory
  honesty element (footer verdict, "structured · not a console" pill,
  sandbox/tracked region labels + SIMULATED strip, respectively).
- `prefers-reduced-motion` and the no-WebGL fallback both degrade to an
  existing, already-designed state (`neural-engine-2d.html`), not an
  undesigned blank screen.
- A UI test asserts no raw stdout/log string is ever rendered (docs/05 §5.3,
  docs/11 §11.12 honesty suite).
