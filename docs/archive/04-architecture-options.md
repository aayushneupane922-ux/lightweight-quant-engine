# 04 — Architecture Options

Four paths, scored against your constraints (solo dev, $0, crypto-first, local desktop window, paper-only, deterministic, testable, Claude-Code-built). Scores are 1–5 (5 = best for *this* project), `[Likely]` unless a cited fact makes them `[Certain]`.

## The four options

- **Option 1 — Custom lightweight event-driven engine.** You own the event loop, clock, order state machine, risk engine, audit log, and paper broker. Open-source enters only as *libraries behind interfaces* (ccxt, DuckDB/Polars, pandas-ta, QuantStats, skfolio…).
- **Option 2 — LEAN as core**, with a lightweight UI/research wrapper.
- **Option 3 — NautilusTrader as core**, with a lightweight UI/research wrapper.
- **Option 4 — Hybrid.** Custom lightweight research/paper engine as the spine, with *optional adapters* to LEAN / Nautilus / vectorbt / Qlib workflows for specific jobs (e.g., vectorbt for sweeps, Nautilus later for live).

## Scoring matrix

| Criterion | 1 Custom | 2 LEAN | 3 Nautilus | 4 Hybrid |
|---|:--:|:--:|:--:|:--:|
| Simplicity | 5 | 2 | 2 | 3 |
| Power (potential ceiling) | 3 | 5 | 5 | 5 |
| Cost ($) | 5 | 4 | 4 | 4 |
| Implementation time (MVP) | 4 | 2 | 2 | 3 |
| Reliability (proven code) | 3 | 5 | 5 | 4 |
| Learning curve | 5 | 2 | 1 | 3 |
| Maintainability (solo) | 5 | 3 | 2 | 4 |
| Testing burden (to *your* standard) | 5 | 2 | 3 | 4 |
| Paper-trading quality (control over fills) | 5 | 4 | 5 | 5 |
| Future live-readiness | 3 | 5 | 5 | 5 |
| Multiple OSS models supported | 4 | 4 | 4 | 5 |
| UI integration (local) | 5 | 3 | 3 | 4 |
| Local-first feasibility | 5 | 3 (Docker) | 4 | 4 |
| Claude Code build suitability | 5 | 3 | 3 | 4 |
| Determinism / replay control | 5 | 3 | 4 | 4 |
| **Total (/75)** | **67** | **50** | **52** | **60** |

### Why the scores land where they do

- **Determinism & replay** — your #4/#6 constraints. Easiest to *guarantee* when you wrote every line (Option 1). Nautilus has strong determinism but you don't control its internals (Option 3). LEAN adds Docker-level non-determinism at the infra layer (Option 2). ([lean-cli Docker requirement](https://github.com/QuantConnect/lean-cli))
- **Risk-gate-on-every-order & live lockout** — your #5. A structural guarantee ("no code path can reach a real broker") is trivial to prove in a core you own and hard to prove inside a framework that *does* ship live adapters. This alone is a strong argument for Option 1/4.
- **Local-first** — LEAN's local runs need Docker; Nautilus is pip-installable without it; the custom engine is just Python. ([Nautilus install](https://nautilustrader.io/docs/latest/getting_started/installation/))
- **Learning curve / maintainability** — a solo dev can hold ~3k lines of their own code in their head; they cannot hold LEAN's C# codebase or Nautilus's Rust core. This is the difference between *maintaining* and *praying*.
- **Power ceiling** — Custom scores lower on raw ceiling, but you don't need LEAN/Nautilus's ceiling for a paper-trading research MVP. You buy the ceiling later via the Hybrid adapters.
- **License friction** (see [`15`](15-open-source-license-review.md)): LEAN Apache-2.0 (clean); Nautilus LGPL-3.0 (handle deliberately for a shipped `.exe`); custom = your license.

## Hidden risks per option

- **Option 1 (Custom):** you can reproduce *classic* backtester bugs (look-ahead, fill optimism, off-by-one on bar timing) if not disciplined. Mitigation: the test plan in [`16`](16-mvp-build-plan.md) and the protocol in [`09`](09-backtesting-research-protocol.md) exist precisely to catch these. Also: "not-invented-here" scope creep — resist rebuilding what a library does well.
- **Option 2 (LEAN):** Docker dependency; opinionated data/universe abstractions; C# center of gravity; you spend your Claude Code budget learning LEAN.
- **Option 3 (Nautilus):** steep concept count; Rust core is opaque for fast iteration; LGPL reasoning for distribution; heavy for a first MVP.
- **Option 4 (Hybrid):** *interface sprawl* — the temptation to wire in LEAN/Nautilus/vectorbt/Qlib all at once. Mitigation: adapters are **stubs/placeholders in MVP**; only ccxt + CSV replay are real on day one.

## Ranked recommendations

- **Best MVP architecture:** **Option 1 (Custom).** Highest total, best fit to the non-negotiables, fastest to a *safe* paper-trading loop you fully understand.
- **Best long-term architecture:** **Option 4 (Hybrid)** — the custom core *is* the spine; you add a `NautilusExecutionAdapter` (and optionally LEAN/Qlib research adapters) when you outgrow the core. Option 1 grows into Option 4 without a rewrite.
- **Cheapest viable architecture:** **Option 1** — pure Python + free libraries + free crypto data; only cost is the Claude Code subscription.
- **Fastest prototype architecture:** **Option 1 for the *engine*.** For fast *research screening only*, bolt on **vectorbt (open)** offline (Option 4 flavor) — but never as the runtime.
- **Most robust (proven-code) architecture:** **Option 3 (Nautilus)** in isolation — but its robustness is bought with complexity you can't yet maintain. Choose it *later*, as the Hybrid's graduation engine.
- **Architecture to avoid:** **anything built on Backtrader** (unmaintained + GPL), and **making vectorbt the runtime engine** (Commons Clause + it isn't an execution engine). Also avoid **Option 2/3 as the MVP core** for a first-time solo build.

## The through-line

> Start at **Option 1**, keep the **Option 4** seams empty-but-defined. You get a simple, cheap, fully-understood, safe MVP now, and a clean upgrade path to institutional-grade engines later — with **no architectural rewrite**, because the strategy/model/data/execution interfaces are identical across both. Details: [`05-recommended-architecture.md`](05-recommended-architecture.md).
