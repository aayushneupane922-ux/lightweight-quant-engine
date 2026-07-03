# 28 — UI/UX Design System: "OBSIDIAN DESK"

The brief: a UI that looks like it came from Goldman / JP Morgan / Bloomberg — **an advanced trading terminal from the future** — showing many quant models operating on live data at once, with **no raw CLI/log feeds in the GUI.** This file is the committed visual + interaction system the developer builds to. A rendered mockup of the hero screen ships alongside it (`mockups/obsidian-desk-model-floor.html`).

> **Bloomberg's own design principle, adopted here:** *conceal complexity.* ([Bloomberg UX](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/)) The power is dense; the surface is calm. Information density without eye fatigue is the whole craft. ([HN: Bloomberg density](https://news.ycombinator.com/item?id=19153875))

## 28.1 Design thesis (one committed direction)
**A precision instrument, not a neon toy.** Deep graphite "glass," hairline structure, one restrained **amber** heritage thread (the nod to the Bloomberg amber), engineered monospace numerics, and **color used only to carry meaning** (long/short, model state, risk, intelligence). The signature is a live **Model Floor** — a grid of model "instrument cells" armed and watching the same feed, firing in real time, with a quiet violet **Intelligence** layer drawing correlations between them. This is deliberately *not* the default "acid-green-on-black dashboard"; green here means only "long/up," never "good."

## 28.2 Color tokens (semantic, disciplined)
```css
/* structure — deep graphite, blue-black undertone */
--void:  #07090D;   /* app background (deepest)         */
--desk:  #0E131B;   /* panel/surface                    */
--slab:  #131A24;   /* raised element (cards, headers)  */
--ridge: #1E2836;   /* hairline borders / dividers      */
--ink:   #E9EEF5;   /* primary text                     */
--mute:  #6B7A90;   /* secondary text, labels, axes     */

/* the single interactive/heritage accent — use sparingly */
--amber: #F0A62A;   /* active nav, focus ring, key CTA, PAPER shield */

/* semantic data channels — ONLY for meaning, never decoration */
--long:  #35C08B;   /* long / up / positive              */
--short: #F0524D;   /* short / down / negative           */
--intel: #7C7BF2;   /* meta-learning / ML "intelligence" */
--warn:  #F0A62A;   /* risk warning (shares amber)       */
--halt:  #F0524D;   /* halted / breach (shares short)    */
```
Rules: (1) if a pixel is colored, it means something — long/short/intel/risk. (2) The **Intelligence** layer always uses `--intel` (violet) so ML output can never be mistaken for performance. (3) Contrast: `--ink` on `--desk` ≥ 12:1; `--mute` on `--desk` ≥ 4.5:1; never encode state by color alone (pair with a glyph/label).

## 28.3 Typography
```css
--font-ui:   "Söhne", "Neue Haas Grotesk", Inter, system-ui, sans-serif; /* free fallback: Inter */
--font-data: "Berkeley Mono", "JetBrains Mono", ui-monospace, monospace; /* free fallback: JetBrains Mono */
```
- **UI face (grotesque):** all labels, nav, prose. Tight tracking (-0.01em) on headings; sentence case; weights 400/500/600 only.
- **Data face (mono, tabular figures):** **every number** — prices, P&L, Sharpe, DSR, times, counts. `font-variant-numeric: tabular-nums;` so columns align and don't jitter as values tick.
- Type scale (px): 11 caption · 12 label · 13 body · 15 subhead · 20 panel-title · 13-mono data · 28 hero readout. Line-height 1.35 body, 1.1 data.
- The mono-numerics + grotesque-UI split *is* the "instrument" feel — do not set numbers in the UI face.

## 28.4 Layout — "the desk" (cockpit)
```
┌────────────────────────────────────────────────────────────────────────────┐
│ STATUS RAIL  ● feed:live  UTC 14:30:05   BTC-USDT 1m   [ PAPER · LIVE LOCKED ]│  ← amber shield, always
│              session P/L (sim) · exposure · drawdown            [ KILL ]      │
├──────┬───────────────────────────────────────────────────────┬───────────────┤
│ MODE │   MODEL FLOOR  (the hero: N instrument cells)          │ INSPECTOR     │
│ spine│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐            │ (drill-in on  │
│ ▸Floor│  │trend   │ │breakout│ │meanrev │ │ vol-tgt│  …10+      │  a model) or  │
│ ·Cat │  │ ▲ARMED │ │ ◆FIRED │ │ ▼SHORT │ │ ·flat  │            │ INTELLIGENCE  │
│ ·Rsch│  │ ╱╲sprkl│ │ ╱╲     │ │ ╲╱     │ │ ──     │            │ narration     │
│ ·Intel│  └────────┘ └────────┘ └────────┘ └────────┘            │ (violet)      │
│ ·Risk│   …intelligence threads (faint violet) link correlated…  │               │
├──────┴───────────────────────────────────────────────────────┴───────────────┤
│ TAPE (optional drawer): designed event rows — NOT a CLI log                    │
└────────────────────────────────────────────────────────────────────────────┘
```
- **Status rail (top, slim):** feed-health dot, UTC market clock (mono), active feed, the **PAPER · LIVE LOCKED** shield (amber, non-dismissible), session sim-P/L, exposure, drawdown, global **KILL**.
- **Mode spine (left, narrow):** Floor · Catalog · Research · Intelligence · Risk. Keyboard/function-key navigable (Bloomberg heritage: `F1..F5`, plus a `⌘K` command palette). Active item in amber.
- **Hero (center): the Model Floor** — see §28.6. This is what the product *is*.
- **Inspector (right):** context panel — drill into one model (signals, "why it traded," positions, metrics) or the **Intelligence** narration.
- **Tape (bottom drawer, optional):** structured event rows (armed/fired/filled/blocked), each a designed row with icon + fields — **never** raw stdout (§28.8).

Grid: 8px base; panels separated by 1px `--ridge` hairlines (no heavy shadows). Density is high but every panel has a quiet header and generous internal rhythm so it scans without fatigue.

## 28.5 Two co-equal modes (from docs/24) mapped to the desk
- **Showcase** = Floor + Catalog + Intelligence (watch models act; browse the library; see what the ML sees).
- **Research** = the validation bench (backtest, cost sweep, DSR/PBO, kill-criteria) — same visual system, denser tables.
- The **bridge** is a persistent action on any model: **▸ Send to Research**. Validated models earn a small amber `★ validated` mark; everything else reads `unproven`.

## 28.6 Signature component — the Model "instrument cell"
Each model on the Floor is a compact instrument (not a chart-heavy card):
- **Header:** family glyph + model name (UI face) + status badge.
- **Stance bar:** a single horizontal bar — center = flat; fills `--long` right or `--short` left by position size. Instant read of "what is it doing right now."
- **State:** `ARMED` (watching, `--mute`), `FIRED` (just triggered — a brief `--amber` pulse), `LONG`/`SHORT` (`--long`/`--short`), `HALTED` (`--halt` + lock glyph).
- **Micro-readouts (mono):** live sim-return (caveated), # trades, and a 24-bar sparkline.
- **Intelligence tint:** a thin left edge in `--intel` whose opacity = the meta-layer's current *conviction* in this model (see docs/29). It's a hint, never a P&L claim.
- **Fire animation:** on trigger, a 400ms amber ring pulse + the tape logs a designed row. Respects `prefers-reduced-motion` (falls back to a static state change).

The **Intelligence threads** (faint violet splines between correlated cells) render only in Intelligence view, so the Floor stays calm by default.

## 28.7 Component inventory (build these)
Data table (tabular mono, sticky header, zebra via 2% `--ink` overlay, sort, right-aligned numerics) · KPI stat (label + big mono readout + delta chip) · sparkline & equity/drawdown charts (1px lines, `--long/--short`, no gridline clutter) · stance bar · state badge/chip · verdict chip (`observing` / `⚠ survives` / `❌ no edge` / `★ validated`) · toast (top-right, quiet) · command palette (`⌘K`) · modal (rare) · the KILL control (amber-bordered, confirm-on-press). No skeuomorphism, no glossy gradients, no drop-shadow stacks.

## 28.8 NON-NEGOTIABLE: no CLI / no raw logs in the GUI
The MVP surfaced a black terminal streaming CLI stdout. **Remove it.** Everything a log would say becomes a **designed, structured component**:
- run progress → a **progress strip** with phase labels ("ingesting · validating · replaying"), not scrolling text.
- results → **tables + KPI stats + charts**, not printed lines.
- events → the **Tape**: one designed row per event (icon, timestamp mono, model, action, detail chips) with filters — sourced from the audit log's structured events, not stdout.
- errors → a **designed inline state** in the interface's own voice (§28.10), never a stack trace dump.
The engine still logs to files for audit/debug; the **GUI never renders raw log/CLI text.** A UI test asserts no element renders unstructured stdout.

## 28.9 Interaction, motion, accessibility (the quality floor)
- **Keyboard-first:** full function-key + `⌘K` palette navigation; visible amber focus ring on every interactive element; logical tab order.
- **Motion:** purposeful only — fire-pulse, 1Hz tape/tick, load-in reveal of the Floor. All gated by `prefers-reduced-motion: reduce` → instant states.
- **Responsive:** the desk is desktop-first (it's a terminal), but degrades to a single-column stack on narrow widths; the inspector becomes a sheet.
- **A11y:** WCAG AA contrast (§28.2); never color-alone (badges carry glyph+label); live regions announce fires/halts politely; charts have text summaries.
- **Localhost, single-user:** no login chrome, no cloud affordances. Nothing implies remote/multi-user.

## 28.10 Copy standard (from the user's side of the screen)
- Name things by what the user controls, never by system internals ("Watch models", "Run backtest", "Stop everything" — not "spawn daemon", "exec CLI").
- **No profit/earnings framing** anywhere; no "Buy/Sell" verbs on controls; keep the "simulated — not evidence of edge" line visible on live views (docs/26 §26.4). Numbers are "simulated return", states are "unproven / validated".
- Errors explain what happened + the fix, in the interface's voice, no apologies, no jargon. Empty states are invitations ("Pick 2–5 models to start a race").
- One action keeps one name end-to-end (the button says "Start race" → the toast says "Race started").

## 28.11 Tech (buildable, permissive, local)
NiceGUI remains the host (docs/13). Implement this system as a **theme layer**: CSS custom properties (the tokens above) + a small component library (NiceGUI custom components / Quasar overrides / injected CSS), charts via ECharts (dark, de-chromed). Fonts: ship **Inter + JetBrains Mono** (free, OFL) as the buildable default; swap in Söhne/Berkeley Mono if licensed. No React rewrite required for the MVP; if the UI later becomes the product, the token system ports 1:1 to a React/Tailwind build (shadcn is a natural fit, as modern Bloomberg-style dashboards use — [ref](https://adminlte.io/blog/fintech-banking-dashboard-templates/)).

## 28.12 Self-critique (per the design process)
- **Not the generic dark-admin default?** ✓ Color is meaning-bound (amber heritage accent + long/short/intel channels), not a lone acid accent; the hero is a bespoke Model Floor, not a KPI-row template.
- **Boldness spent in one place?** ✓ The signature (instrument cells + intelligence threads); everything else is quiet hairline structure.
- **Honors the brief exactly?** ✓ Bloomberg density + amber + mono numerics + function-key/command-palette navigation + "conceal complexity," modernized into a precision instrument.
- **Removes an accessory?** Cut: no ambient background animation, no glow stacks, no gradient chrome — they'd read as "AI dashboard," not "institution-grade instrument."
