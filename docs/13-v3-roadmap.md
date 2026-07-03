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

## M18 — Zero-CLI, one-click launch  · M · Dep: v2.0
**Goal:** the user double-clicks one thing; everything the CLI used to do
happens automatically, and they land on a ready dashboard. No terminal,
ever.

- [ ] **Single entry point** (double-clickable per OS: `.command`/`.bat`, or
  a pywebview/PyTauri desktop app). It: (a) ensures the environment/deps
  (bundle them, or run a one-time setup with a visible progress screen), (b)
  runs `lqe doctor` + first-run setup (auto-ingest a small default dataset
  if none exists), (c) starts the FastAPI server on `127.0.0.1`, (d) opens
  the browser (or a native window) to the dashboard.
- [ ] **Friendly onboarding/status screen** during startup — plain-language
  progress ("Preparing data… Starting engine… Opening dashboard"), not a
  terminal, not raw stdout. Errors are designed states ("Couldn't reach the
  exchange — retrying"), never stack traces.
- [ ] **Move every operation into the GUI** via the *existing whitelisted
  control path*: ingest, backtest, start/stop live, autopilot on/off,
  resume. These are buttons that trigger the same gated actions in a
  background worker — **they add no new capability and construct no
  `Order`.**
- [ ] **Session control:** persist last session (M15 already resumes
  state); offer a visible "Resume last session?" choice on launch. Never
  auto-start anything surprising — land on a ready dashboard with an
  obvious **Start** control.
- [ ] Keep it fully **offline/local** — no CDN, no network calls except
  ccxt public + optional local Ollama.
- **Tests:** with no prior setup, launch → ready dashboard; every former
  CLI op is reachable from the GUI; the new buttons construct no `Order`
  (extend `tests/safety`); bound to `127.0.0.1` only; onboarding renders
  status, never raw stdout.
- **Exit gate:** a non-technical user goes double-click → live dashboard
  with zero terminal use; safety tests green. `git tag m18-done`.

## M19 — Institutional UI/UX polish (Obsidian Desk, applied)  · L · Dep: M18
**Goal:** it doesn't just work — it looks like a Goldman/Bloomberg-grade
instrument. Apply the design system to the *built* FastAPI + Jinja + WebSocket
UI. The `ui-ux-pro-max` engine independently recommended this exact profile
(Dark-OLED · dense dashboard · status colors · mono numerics), which
confirms the direction.

**Design system (build to this):**
- **Direction:** "Obsidian Desk" — deep graphite, **one** amber heritage
  accent, **color only ever means something** (long / short / intelligence
  / risk). Full spec: `archive/28-ui-ux-design-system.md`.
- **Color tokens (CSS custom properties):** `--void #07090D` · `--desk
  #0E131B` · `--slab #131A24` · `--ridge #1E2836` · `--ink #E9EEF5` ·
  `--mute #6B7A90` · `--amber #F0A62A`; semantic `--long #35C08B` (bullish)
  · `--short #F0524D` (bearish) · `--intel #7C7BF2`. Every text pair ≥
  4.5:1; **never color-alone** — pair with a glyph/label.
- **Typography:** a grotesque sans for UI (Inter or **Fira Sans**), an
  engineered mono for **every number** (**JetBrains Mono** / Fira Code)
  with `font-variant-numeric: tabular-nums` so columns don't jitter as
  values tick. Scale 12/14/16/20/28.
- **Layout:** the "desk" cockpit — status rail (feed health, UTC clock,
  **PAPER · LIVE LOCKED** amber shield, session sim-P/L, KILL), left mode
  spine (Floor · Catalog · Research · Intel · **Engine 3D** · Risk ·
  **Blotter**) with `F1..F7` + `⌘K` command palette, center hero, right
  inspector, bottom Tape. **Density 8/10** — dense but scannable.
  Institutional hierarchy: live prices/P&L **top, large, high-contrast**;
  secondary metrics muted below.
- **Charts:** for equity/price/candlestick/streaming, either keep
  hand-rolled canvas (zero-dep, consistent with the force-graph) **or
  vendor TradingView Lightweight Charts** (Apache-2.0 → ALLOW under the
  license gate; offline-vendorable; the institutional standard for
  financial charts — recommended for candlesticks/streaming, which are
  painful to hand-roll well). Bullish `#26A69A` / bearish `#EF5350` with
  **fill-vs-outline** so it survives colorblindness; real-time = streaming
  area with a **pause/resume** control and the current value as a big KPI;
  **data-table fallback** for a11y; downsample > 1000 points.
- **Motion 4/10:** 150–300ms micro-interactions, ease-out enter / ease-in
  exit, the fire-pulse; **respect `prefers-reduced-motion`.**
- **A11y:** WCAG AA contrast, visible focus rings, keyboard-first,
  reduced-motion, tabular numbers, no emoji-as-icon (SVG only), chart
  data-table fallback.
- **Tasks:** extract tokens to CSS variables; build a small component
  library (tables with sticky header + `aria-sort`, KPI cards, badges,
  verdict chips, toasts with `aria-live`, command palette); apply across
  all views; polish empty/loading/error states; dark-only (no light mode
  needed).
- **Tests:** AA contrast on all text; focus visible; reduced-motion
  honored; numbers tabular; no emoji icons; visual review against the
  Obsidian Desk mockups.
- **Exit gate:** the UI matches the design system, scans like an
  institutional terminal, passes a11y. `git tag m19-done`.

## M20 — Live Trade Blotter (the trade book you can watch)  · M · Dep: M19
**Goal:** when a trade happens, you *see* it — unmistakably. (This is very
likely a display/plumbing gap, not a trading gap — the fix includes proving
trades actually flow.)

- [ ] A first-class **Blotter** view + a compact live **Tape** strip on the
  Floor. One row per fill, newest on top, live via WebSocket. Columns
  (mono, tabular): time · model · symbol · side (long/short color **+**
  glyph) · qty · fill price · fee · slippage bps · sim P&L. Filter by
  model/symbol/side; per-model and aggregate tabs.
- [ ] Show the **full order lifecycle**, not just fills: intent → **risk
  decision** (APPROVE / CLAMP / REJECT + reason) → fill / partial / reject.
  So the user sees *why* something did or didn't trade.
- [ ] **Unmissable feedback:** a new fill flashes its row + a quiet toast;
  the Floor cell pulses. Optional subtle sound, **off by default**.
- [ ] **Honest empty state (do not skip — this is probably the actual
  complaint).** If there are no trades, say *why*: "Warming up — N bars
  until first evaluation" / "No signals in the last X min (models are
  watching)" / "Tracked book has 0 promoted models — exploring in the
  sandbox." Never a blank panel that looks broken.
- [ ] **Verify trades genuinely flow** (fix the cause, not just the view):
  a task/test that runs the live fleet over a replay or live window and
  asserts fills reach the blotter. If the fleet legitimately isn't trading,
  surface that state in plain language.
- [ ] **Reconciliation panel:** positions / cash / P&L per model, tied out
  to the audit log (standard blotter practice).
- **Tests:** every fill in the audit log appears in the blotter, in order;
  lifecycle (reject/clamp with reason) shown; the empty state explains
  *why*; a live/replay session produces visible fills; the blotter is
  read-only (constructs no `Order`).
- **Exit gate:** you can watch trades happen live with clear per-trade
  detail and an honest empty state. `git tag m20-done`.

## M21 — The "Engine Room" conversation (watch the LLM, ML & autopilot talk)  · L · Dep: M19
**Goal:** witness the LLM, the optimizer, the validator, and the autopilot
communicate — in plain English, live, no code or cryptic IDs. (Agent-UX
research: showing intermediate steps as inline "tool-call cards" kills the
black-box feeling; the interface is the *accountability layer* between
intent and autonomous action.)

- [ ] A **conversation/timeline feed** rendered as a readable dialogue
  between named participants: **Strategist (LLM)** · **Optimizer (Optuna)**
  · **Judge (Validator)** · **Autopilot** · **Risk**. Each turn = one
  plain-language sentence **+** a compact "what it did" card. Example of
  one loop iteration:
  - **Strategist:** "Volatility on BTC is climbing — I'll test wider
    breakout lookbacks (20–80) with tighter stops."
  - **Optimizer:** `card` "Ran 60 trials · best Sharpe 1.42 @ lookback 48"
  - **Judge:** `card` "❌ Failed — DSR 0.10, PBO 0.71, doesn't beat
    equal-weight after costs"
  - **Autopilot:** "Discarding this idea, logging the hypothesis, moving on
    to mean-reversion."
- [ ] Every loop step (OBSERVE → HYPOTHESIZE → SEARCH → VALIDATE → DECIDE →
  NARRATE) becomes one or more messages, timestamped, **color-coded by
  participant** (Strategist = `--intel` violet; Judge = long/short by
  verdict; Autopilot = `--amber`; Risk = `--short` on breach). **No code,
  no JSON, no cryptic IDs** in the default view — a "Details" disclosure
  can reveal params for power users.
- [ ] **Honesty is structural, not decorative:** the **Judge (deterministic
  math) is visibly the one who *decides*;** the Strategist only proposes
  and explains. Promotions show the validation evidence. Keep the
  "simulated · not evidence of edge" line. This *is* the loop invariant made
  visible — LLM steers, math decides.
- [ ] **Works without the LLM:** when Ollama is absent, the **templated
  narrator** produces the same plain-language messages — the participants
  still "speak," just from templates. The feed is never empty or broken.
- [ ] **Accountability + control:** the human can **pause / kill** right
  from this view (the research's "intervention point"); kill and de-risk
  events appear as messages too.
- [ ] **Source + replay:** built from the existing `NarrationEvent` +
  autonomy events in the audit log via `StateReader`. Because runs are
  deterministic, a **timeline scrubber replays the entire conversation** of
  any past session, exactly.
- **Tests:** every autonomy event yields a readable message; the feed
  reproduces deterministically on replay; it works with the LLM absent
  (templated); no raw JSON/stdout in the default view; only the
  Judge/Validator can emit a "validated" verdict (matches the safety
  model); pause/kill reachable from the feed.
- **Exit gate:** you can watch the LLM ↔ ML ↔ autopilot converse in plain
  English, live and on replay, honestly. `git tag m21-done`.

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
