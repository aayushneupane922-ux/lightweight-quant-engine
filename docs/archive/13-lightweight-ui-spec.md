# 13 — Lightweight UI Spec

**Constraint (#8):** lightweight, local-first, *not* a SaaS dashboard. **Packaging (your choice):** a **local app in a desktop window** — a localhost UI wrapped in a native window, single-user, nothing exposed to a network. **Decision: NiceGUI for the MVP**, later wrapped with **pywebview → PyTauri** into a Windows `.exe`. Streamlit is kept as a secondary tool for research reports.

## 13.1 UI option comparison

| Option | Build speed | Maintainability | Local-first | Charting | Interactivity | Auth needs | Complexity | Claude Code fit | Recommended role |
|---|---|---|---|---|---|---|---|---|---|
| **NiceGUI** (MIT) | Fast | Good | Excellent | ECharts/Plotly/AGGrid | **High (WebSocket live)** | none (local) | Low–med | **High** | **MVP app UI** |
| **Streamlit** (Apache-2.0) | **Fastest** | Good (small apps) | Good | Rich built-ins | Medium (rerun model) | none (local) | Low | High | Research reports / notebooks-as-apps |
| FastAPI + HTMX | Medium | High | Excellent | via JS libs | High | DIY | Medium | Medium | If you want max control / minimal deps |
| Dash (MIT) | Medium | Medium | Good | Plotly (excellent) | High (callbacks) | none (local) | Medium | Medium | Chart-heavy analytics alt |
| Textual (MIT) | Medium | Good | **Excellent (TUI)** | weak (ASCII/export) | Medium | none | Low–med | High | Optional headless/daemon TUI |
| React/Vite front end | Slow | Med–high | Good | best-in-class | Highest | DIY | **High** | Medium | Overkill for MVP; only if UI becomes the product |
| Gradio (Apache-2.0) | Fast | Med | Good | ML-demo-oriented | Medium | none | Low | High | Not a fit (built for ML demos) |

### Why NiceGUI for the MVP
- **App-style, stateful, real-time.** Built on FastAPI + Vue with WebSocket updates — ideal for a live paper-trading monitor where equity, blotter, and risk status must tick without page reloads. Streamlit's rerun-the-whole-script model fights stateful live views. ([NiceGUI vs Streamlit](https://www.bitdoze.com/streamlit-vs-nicegui/))
- **MIT-licensed, self-hosting-first, no cloud.** ([NiceGUI](https://nicegui.io))
- **Windows-window packaging** is well-trodden: NiceGUI runs in a pywebview native window today, and PyTauri can bundle a NiceGUI app into a standalone `.exe` without Node/Rust hand-holding (via `pytauri-wheel`). ([PyTauri + NiceGUI](https://github.com/pytauri/pytauri))
- **Good charting** via ECharts/Plotly/Highcharts and AGGrid tables — enough for equity/drawdown/blotter without a React build.

### Why Streamlit stays (secondary)
Fastest way to turn a research notebook into a shareable local report (parameter sweeps, tearsheets). Use it for **offline research artifacts**, not the live trading monitor.

## 13.2 Views the MVP UI must provide

Organized into three areas; all read from DuckDB/audit + issue control commands.

**A. Research & backtest**
- **Strategy list** — registered strategies + param schemas + descriptions.
- **Experiment list** — the registry ([`09`](09-backtesting-research-protocol.md) §9.10): run_id, strategy, params, Sharpe/DSR/PBO/maxDD/turnover, passed-kill-check.
- **Backtest runs** — launch/inspect a run; **equity curve**; **drawdown chart**; trade blotter; metrics tearsheet (QuantStats).
- **Strategy comparison** — overlay equity curves + metric table across runs.
- **Model comparison** — compare model/optimizer variants side-by-side.
- **Parameter-sweep results** — heatmap/table of a sweep (plateau vs. spike, per [`09`](09-backtesting-research-protocol.md) §9.7).

**B. Paper-trading monitor (live-updating)**
- **Paper-trading status** — running/stopped, session clock, current equity/PnL.
- **Positions** — per-symbol qty, avg px, unrealized PnL.
- **Orders** — working/filled/rejected with reasons.
- **Trade blotter** — chronological fills with fees/slippage.
- **Event-log viewer** — filterable stream from the audit log.
- **Risk status** — daily PnL vs. limit, gross exposure vs. cap, order counts, breaches.
- **Kill-switch status + button** — big, obvious; one-click KILL (and FLATTEN); shows `kill_active` prominently.
- **Data health** — feed freshness (stale flags), gaps, last bar per symbol.

**C. Config & reporting**
- **Configuration viewer** — the loaded config (read-only in MVP; edits via file + reload) with the **live-lockout status shown explicitly** ("Mode: PAPER · Live trading: LOCKED").
- **Daily report** — the generated session report ([`10`](10-paper-trading-engine-spec.md) §10.13).

## 13.3 UI ↔ engine boundary (safety-relevant)

- The UI is a **separate process**. It **reads** state (DuckDB + audit JSONL) and **sends only whitelisted control commands** (START/STOP/**KILL**/FLATTEN) over a tiny local IPC (file flag or localhost socket bound to `127.0.0.1`).
- The UI **cannot construct orders** or bypass the risk engine — it can only ask the daemon to start/stop/kill. All order logic stays server-side behind the risk gate.
- The UI **never holds credentials** (there are none in MVP) and never talks to an exchange for trading (read-only market data at most).
- Nothing is exposed beyond localhost; no auth is needed because nothing is remotely reachable. If you ever expose it, that's a new threat model — out of MVP scope.

## 13.4 Charting & performance

- Equity/drawdown: line/area via ECharts or Plotly; downsample long series for responsiveness.
- Blotter/positions/experiments: AGGrid or NiceGUI tables with sort/filter.
- Live updates via WebSocket push on new audit events; throttle to human-readable refresh (e.g., 1–2 Hz), not every tick.

## 13.5 Recommendation

- **Best UI for MVP:** **NiceGUI** (localhost), packaged later into a Windows desktop window via **pywebview**, then **PyTauri** for a distributable `.exe`.
- **Best UI for later:** stay on NiceGUI; only move to a **React/Vite** front end if the UI itself becomes a product with multi-user/remote needs (adds auth, hosting, and a threat model you don't want in MVP).
- **Keep Streamlit** in the toolbox for quick research reports and sweep visualizations.
- **Optional:** a **Textual** TUI for a headless server/daemon view if you run the paper daemon without a GUI.

> **Lightweight test:** if the UI needs its own database, auth system, or cloud deploy to run, it's too heavy. The MVP UI is a *window onto local files + a kill button* — nothing more.
