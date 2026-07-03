# 05 — UI & 3D Visualization (FINAL)

Two surfaces in one `localhost` web app: the **Obsidian Desk** terminal (dense, institution-grade, function-key driven) and a dedicated **3D neural-web** space to *watch the engine think*. No CLI/stdout anywhere. Full design-token detail: [`archive/28-ui-ux-design-system.md`](archive/28-ui-ux-design-system.md); rendered terminal mockup: [`mockups/obsidian-desk-model-floor.html`](../mockups/obsidian-desk-model-floor.html); 3D mockup: [`mockups/neural-engine-3d.html`](../mockups/neural-engine-3d.html).

## 5.1 Design system recap ("Obsidian Desk")
Deep graphite (`--void #07090D`, `--desk #0E131B`), one restrained **amber** heritage accent (`#F0A62A`), engineered mono numerics (JetBrains/Berkeley Mono, tabular figures), hairline structure. **Color only means something:** `--long #35C08B`, `--short #F0524D`, `--intel #7C7BF2` (the ML/LLM channel — so intelligence never masquerades as P&L). WCAG AA; keyboard-first; `prefers-reduced-motion` respected. Full tokens/components in the archive doc.

## 5.2 Navigation (the "desk")
Top status rail (feed health, UTC clock, **PAPER · LIVE LOCKED** amber shield, session sim-P/L, **Autopilot** toggle, **KILL/freeze**). Left mode spine (`F1..F6`): **Floor · Catalog · Research · Intelligence · Engine (3D) · Risk**. Right inspector (drill-in / narration). Optional bottom **Tape** (structured event rows). `⌘K` command palette.

## 5.3 NON-NEGOTIABLE: no CLI/logs in the GUI
Everything a log would print becomes a designed component: run progress → a **phase strip**; results → **tables/KPIs/charts**; events → the **Tape** (one designed row per audit event, filterable); errors → a designed inline state in the product's voice. The engine still logs to files; the GUI renders **no raw stdout**. A UI test asserts this.

## 5.4 The Autopilot experience
- A prominent **Autopilot** switch in the status rail. **ON** → an "autonomous" state: the LLM's live actions stream as designed **decision cards** (hypothesis → search → validate → promote/kill), the 3D engine animates, and you're a passenger. **OFF** → parameter controls unlock for manual tuning.
- A persistent **"take the wheel"** affordance and a human **KILL/freeze** that halts autonomy instantly (survives restart).
- Honest framing throughout: sandbox vs tracked clearly separated; the watched **tracked equity curve** is labeled with its validation provenance; no "profit/earnings" language.

## 5.5 The 3D neural-web visualization (the dedicated "watch it work" space)
A full-screen WebGL scene — a living, force-directed web of the *real* system state. Built with **three.js + `3d-force-graph`** (ThreeJS/WebGL, d3-force-3d physics, MIT). ([3d-force-graph](https://github.com/vasturiano/3d-force-graph), [react-force-graph](https://github.com/vasturiano/react-force-graph))

**What the nodes/edges actually represent (honest telemetry, not a fake brain):**
- **Model nodes** — one per active model; size = capital/attention, color = state (`--long/--short/--mute`), a `--intel` halo = the meta-layer's current conviction. Firing = a pulse.
- **Regime/feature nodes** — current market-regime and feature states feeding the models.
- **Edges** — live **correlations** between models (thickness/opacity = strength), and **data-flow** links (feed → models → risk → book) that animate as events pass.
- **The meta-layer / LLM** — a distinct `--intel` cluster whose links to model nodes brighten as it attends to / tunes them; promotion events travel a visible edge from sandbox → tracked book.
- **Sandbox vs tracked** — two visually distinct regions (dim exploratory swarm vs. the bright, validated tracked core), so you *see* the discipline: lots of churn in the sandbox, only validated configs crossing into the tracked core.

**Interaction:** orbit/zoom/drag nodes (force sim reheats), click a node → inspector detail, hover → tooltip, timeline scrubber to replay a session from the audit log (determinism makes this exact). Performance: instanced meshes for many nodes; throttle to ~1–2 Hz updates; `prefers-reduced-motion` → a calm static layout. Degrades to the 2D Floor on weak GPUs.

**Honesty overlays (mandatory, even here):** a persistent "SIMULATED — not evidence of edge" mark; node/edge stats show sample sizes; a rising tracked core is labeled "validated OOS," a churning sandbox is labeled "exploratory / unvalidated." The 3D space is the most seductive screen in the product — it must be the most honest.

## 5.6 The core views (unchanged in intent)
Floor (live model instrument cells), Catalog (browse/search the library), Research (backtest + the validation gate evidence), Intelligence (who-works-when matrix, drift, LLM narration), **Engine (the 3D web)**, Risk (limits, exposure, kill state), Daily report. Each carries the honesty layer.

## 5.7 Tech & acceptance
- FastAPI + NiceGUI (localhost) for the terminal; a WebGL canvas (three.js + `3d-force-graph`) for the 3D space, fed by the same StateReader/WebSocket. All MIT/permissive.
- **Acceptance:** the app looks like the Obsidian Desk mockup; the 3D space animates real model/correlation/flow state from the audit log and replays deterministically; sandbox vs tracked are visually distinct; **no CLI/stdout anywhere**; honesty overlays present; `127.0.0.1` only.
