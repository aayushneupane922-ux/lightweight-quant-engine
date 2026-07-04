# System Handoff — `lightweight-quant-engine` (v4.0)

> **What this document is:** a complete, standalone explanation of the whole
> product — what it is, what it does, and how it works — written to be
> readable by two different people: someone with **no coding background** who
> wants to understand what they're looking at, and a **developer** who needs
> to actually work on the code. Plain-language sections come first in every
> chapter; technical depth follows. If you only want one or the other, skim
> for the `**Developer note:**` callouts and skip (or seek out) those.
>
> This file is current as of **v4.0** (tag `v4.0`, commit `c170a9c`). For the
> terser, session-to-session engineering log, see `HANDOFF.md`. For a
> step-by-step "how do I run X" guide, see `USER-GUIDE.md`. For a
> module-by-module deep dive, see `COMPONENT-GUIDE.md`.

---

## 1. What is this, in plain English?

Imagine you wanted to test a hundred different ideas for trading
cryptocurrency — "buy when the price breaks out of its recent range," "buy
when it's cheaper than its 20-day average," "buy the coin that's been
lagging its peers," and so on — without ever risking a single real dollar,
and without having to babysit a hundred spreadsheets yourself.

That's what this is. It's a **simulator**: a program that runs on your own
computer, watches real (or replayed) cryptocurrency price data, and lets a
large library of trading strategies "trade" against that data using
**pretend money**. Every strategy gets its own imaginary account. Nothing it
does ever touches a real exchange, a real bank account, or a real broker —
there is no code path in this program that *can* place a real order, the
same way a flight simulator has no code path that can actually take off.

On top of that, the system has an **automated research assistant** (part
rule-based logic, part an optional local AI model) that continuously:
1. **Tries out** variations of each strategy's settings,
2. **Tests** each variation honestly against data it hasn't "seen" yet
   (the trading equivalent of a pop quiz, not an open-book exam),
3. **Promotes** only the ones that pass a strict statistical bar to a
   "real" (still pretend-money) tracked portfolio you can watch,
4. **Explains**, in plain sentences, what it just did and why.

You can watch all of this happen live in a web dashboard running on your own
machine (nothing is sent anywhere else) — a home-page-style grid of every
strategy's current pretend position, a live trade ledger, a 3D visualization
of the whole "engine room," and a running conversation feed narrating every
decision the system makes.

**The one sentence that matters:** the system *learns* by testing ideas
against history, only lets a *proven* idea run against live data, watches
that live performance for signs of decay, and goes back to testing when it
decays — a person can watch and steer, but the arithmetic (not a gut feeling,
and not the AI) decides what's actually working.

**Developer note:** "paper-only" isn't a setting someone could accidentally
flip — it's structural. Exactly one class in the whole codebase
(`PaperBroker`) is capable of executing an order, no real-broker SDK is
imported anywhere, and a repo-wide automated test parses the source code
itself (an AST scan, not just a text search) to prove no other order path
exists. See §3 for the full list of these structural guarantees.

---

## 2. Why would anyone want this?

Two honest reasons, neither of which is "to make money trading":

- **It's a safe place to learn what actually works** in systematic trading
  research — you get to see, first-hand, that most simple trading ideas
  don't survive honest, out-of-sample testing, without losing anything to
  find that out.
- **It's genuinely satisfying to watch.** A large simulated "engine room" of
  strategies, an AI narrating its own research process in plain sentences, a
  3D visualization of a hundred models thinking at once — it's built to be a
  good demo of what an autonomous research loop looks like, honestly
  represented (no invented profits, no hidden risk).

It is explicitly **not** a signal service, not investment advice, and not a
claim that any strategy in it is profitable. Every screen in the dashboard
says so, in words, not fine print.

---

## 3. The rules this system never breaks

These are the promises the whole product is built around. Every single one
is enforced by an automated test — most of them by a program that reads the
source code itself looking for violations, not just a runtime check that
could theoretically be skipped.

| # | The promise | In plain terms |
|---|---|---|
| 1 | **Paper-only, always.** | It is architecturally incapable of placing a real trade — there's no real-broker code in the program at all, not just a switch turned off. |
| 2 | **Everything is recorded and reproducible.** | Every single thing that happens — every price tick, every decision, every simulated trade — is written to a tamper-evident log (each entry is cryptographically chained to the one before it, like a lightweight blockchain). Run it twice with the same inputs, get byte-identical results. |
| 3 | **Nothing is called "proven" without passing a real test.** | A strategy only earns the label "validated" after surviving a battery of statistical tests designed specifically to catch lucky-but-fake results (explained in plain terms in §7). |
| 4 | **Two separate playgrounds, never confused.** | Untested ideas trade in a clearly-labeled "sandbox." Only validated ideas reach the "tracked" portfolio that the headline equity curve is drawn from. The dashboard never blends the two. |
| 5 | **The AI never grades its own homework.** | An optional AI model can suggest what to try next and narrate what happened in plain English. It never gets to decide a strategy passed, and it never gets to size or place a trade — those decisions are made by fixed, auditable math, not by the AI's judgment. |
| 6 | **A human can always slam the brakes, and the AI can't override it.** | A "kill switch" file, owned by a human, stops all new trading the instant it's set. It only clears when a named person clears it. The AI's entire vocabulary of possible actions doesn't include "clear the kill switch" or "place an order" — the capability doesn't exist for it to reach for, not just a permission it's denied. |
| 7 | **The dashboard shows nothing but what actually happened.** | No fabricated demo data, no hidden terminal output, nothing claiming a profit that isn't from the validated, tracked book. |
| 8 | **Every piece of software this runs on is legally checked.** | Before anything ships, an automated scan checks the license of every library used (and everything *that* library depends on) and refuses to proceed if anything has a license that would be a legal problem to redistribute. |
| 9 | **Local and free to run.** | No cloud service, no subscription, no API key required for the core product — it runs entirely on one machine. |

**Developer note:** these map directly to `GUARDRAILS.md`'s "never violate"
list and `CLAUDE.md`'s "9 non-negotiables." Every release (v1.0 through
v4.0) re-runs a full safety + honesty audit against this exact list before
being tagged — see `M12-RELEASE-REVIEW.md`, `V2-RELEASE-REVIEW.md`,
`V3-RELEASE-REVIEW.md`, and `V4-RELEASE-REVIEW.md` for the evidence trail.

---

## 4. How it actually works

### 4.1 The loop, in plain terms

```
   Historical data  →  try lots of variations  →  test each one honestly
         ↑                                              │
         │                                    does it pass the bar?
   go back and                                          │
   re-test if a                              ┌──── no ──┴── yes ────┐
   live strategy                              ▼                     ▼
   starts to decay                    quarantine it,        promote it to the
                                       explain why           "tracked" portfolio
                                                                      │
                                                                      ▼
                                                     it now runs against real-
                                                     time (still paper) data,
                                                     continuously watched for
                                                     signs it's stopped working
```

An always-on "autopilot" runs this loop continuously and aggressively —
proposing new things to try, running the tests, promoting or rejecting, and
narrating each step — while a human can watch, pause it, or take manual
control of any single decision at any time.

### 4.2 The architecture, for a developer

```
 ingest (ccxt public market data, or a local CSV replay)
        │
        ▼
 curated Parquet + DuckDB catalog → checksummed, frozen "replay bundle"
        │
        ├──────────────┬───────────────────┐
        ▼              ▼                   ▼
   lqe backtest   lqe autopilot        lqe live
 (one strategy,   (search+validate+   (the WHOLE catalog,
  one pass)        promote loop,       one paper book per
                    looped)             model, real-time or
                                         replayed data, autonomy
                                         loop narrating live)
        │              │                   │
        └──────────────┴───────────────────┘
                        ▼
         hash-chained AuditLog (JSONL, tamper-evident)
                        │
                        ▼
          StateReader (pure read-only replay of the log)
                        │
                        ▼
        Obsidian Desk — FastAPI + WebSocket, 127.0.0.1 only
     Floor · Catalog · Research · Intel · Engine (3D) · Risk · Daily
```

**Core spine** (built in-house, deliberately small and auditable): the event
bus and hash-chained audit log; the deterministic clock abstraction (so a
backtest and a live run share identical logic); `Context`/`Session`, the
per-bar decision loop every strategy runs inside; `make_order`, the single
function that can ever construct a tradeable order; `Accounting`, the
Decimal-precision (never floating-point) ledger; `RiskModel` + `KillSwitch`,
the pre-trade gate and human override.

**Everything else is a thin adapter over a well-known library**, kept behind
a narrow interface so it can be swapped or removed without touching the
spine: `ccxt` for market data (read-only — no order methods are ever called),
`numpy` for the core statistics, `statsmodels`/`arch`/`hmmlearn`/`ruptures`/
`scikit-learn`/`LightGBM` for the more advanced model families, `Optuna` for
hyperparameter search, `FastAPI`+`Jinja2` for the dashboard, a dependency-free
`<canvas>` scene for the 3D view, and an *optional* local Ollama LLM reached
over loopback HTTP (the system works completely fine with no LLM installed —
it falls back to plain, rule-based narration).

**Developer note:** the layering is enforced, not just documented —
`tests/safety/test_module_layering.py` scans imports and fails if, say, the
UI layer ever reaches into `risk`/`execution`/`autonomy` internals directly,
or if `storage` ever imports `data`. `COMPONENT-GUIDE.md` is the full,
file-by-file version of this section.

---

## 5. The model catalog — and what "diversification" actually means here

### 5.1 In plain terms

Early on, this system had about a dozen trading strategies. By v4.0, it has
**104** — but the number 104 is not really the point, and the project is
explicit about that.

Here's the problem with just counting: if you have 50 strategies that are
all secretly "buy when the price is trending up," measured on slightly
different time windows, you don't actually have 50 different bets — you
have **one** bet, worn as 50 costumes. If that one underlying idea stops
working, all 50 fail together.

Real diversification means having strategies that make money (or lose money)
for genuinely *different reasons* — so that when one kind of bet goes
through a rough patch, the others aren't affected the same way. This system
groups every strategy into a **"sleeve"** — its actual return driver — and
measures, with real math (correlation, not vibes), how independent those
sleeves really are from each other.

As of v4.0, the 104 models span **12 sleeves**: classic trend-following and
momentum, mean-reversion, "buy whichever coin is relatively strongest/
cheapest/calmest right now" (cross-sectional), statistical arbitrage between
related instruments, volatility-driven bets, funding-rate/"carry" bets on
perpetual futures, breakout/range strategies, calendar/seasonality effects,
regime-switching overlays, machine-learning-driven signals, portfolio
allocators, and one deliberately weak "always just buy and hold" model kept
around specifically so the tooling has something obviously bad to correctly
reject.

### 5.2 An honest result, not a marketing claim

When this diversification was actually measured — running every model
through a real simulated backtest and computing the real correlation between
them — the results were **genuinely mixed**, and the project's own
documentation says so plainly rather than spinning it:

- The catalog does span the target range of low-correlation "sleeves"
  (11-12, comfortably above the 8-10 target).
- The average correlation between models came in at about **0.37** —
  slightly *above* the aspirational target of "under 0.3."
- One specific sleeve (funding/"carry" strategies) was *hoped* to be a
  crown-jewel diversifier, but measured **more** correlated to the
  directional strategies than average, not less — because it can only ever
  hold one leg of what's normally a two-sided trade (see §5.3).
- A "would this be flagged as a near-duplicate?" check found that **47%**
  of the catalog would be flagged as redundant on the specific test window
  used — some of that is genuine near-duplication (worth pruning), and some
  of it turned out to be an artifact of the short test window (several very
  different strategies happened to all just "buy and hold" for that whole
  window, making them look identical when they aren't, generally).

None of this is hidden. It's written up in detail in `docs/14-v4-catalog-
expansion.md` and `V4-RELEASE-REVIEW.md`, because the whole point of
measuring is to find out the truth, not to confirm what you hoped.

### 5.3 Why the "carry" strategies are honestly limited

**Developer note, but readable by anyone:** a classic "carry trade" earns
money from a *funding payment*, independent of whether the price goes up or
down — you go long the asset in one market and short an equivalent amount in
another, and the two price movements cancel out, leaving just the funding
payment as profit. This system's short-selling code path has **never been
exercised by any model** — going short is a structural non-goal so far, not
an oversight — so the four "carry"-sleeve strategies in this catalog can only
ever hold the *long* leg, gated by a signal derived from funding data. That
means their returns are still ordinary price movement, just gated by a
different signal — an honest simplification, declared in each model's own
`failure_modes` field, not silently glossed over. Building a true,
market-neutral carry strategy would require deciding, as a separate and
significant project decision, whether to ever support real short-selling.

---

## 6. What's been built — the whole journey, condensed

| Version | Milestones | What it added |
|---|---|---|
| **v1.0** | M0–M12 | The whole core: the deterministic event engine, data ingest, the paper broker + accounting, **the promotion gate** (the real heart of the honesty model), the risk model + human kill switch, an 11-model catalog, the first web dashboard, the autonomy loop (search → validate → promote), the optional LLM narrator, the 3D visualization, and a scaled-up 51-model catalog. |
| **v2.0** | M13–M17 | Finished the 51-model catalog, made `lqe live` (running the whole catalog against real-time data) a first-class command, added crash/restart recovery that's provably exact (byte-identical resume), and added automated test coverage for the LLM and heavy-statistics code paths. |
| **v3.0** | M18–M22 | A true one-click launcher (no command line needed), a full visual redesign (the "Obsidian Desk"), a live trade ledger you can watch fill-by-fill, and the "Engine Room" — a turn-by-turn readable conversation feed of the AI's own research process. |
| **v4.0** | M23–M25 | The catalog expansion described in §5: grew from 51 to **104 models across 12 sleeves**, added the ability for a strategy to see *other* instruments' prices (not just its own) for the first time, added a real perpetual-funding-rate data pipeline, and — critically — actually **measured** the diversification claim with real math instead of just adding more models and assuming it helped. Two of those measurements came back short of the hoped-for target and are disclosed plainly rather than reframed (§5.2). |

Every milestone above is committed to git and tagged (`m0-done` through
`m25-done`, plus `v0.1`/`v1.0`/`v2.0`/`v3.0`/`v4.0`) — nothing above is
aspirational or in-progress; all of it is built, tested, and verified.

**Post-v4.0 hardening (not a version bump — the same v4.0 catalog/behavior,
made more correct and faster to use):**

- **A whole-system audit + UI/UX sweep** found and fixed two real
  inconsistencies: the desk never showed a model's *sleeve*, only its
  *family*, even though sleeve is the actual diversification unit v4.0's
  whole story is about; and `lqe live`'s "no bars returned" error didn't
  explain the most likely real cause. It also found (and fixed, then
  removed outright at the user's request, since it duplicated the
  existing keyboard navigation) a command-palette UI feature that a CSS
  bug had left permanently stuck open on top of the dashboard.
- **A 4-phase performance overhaul**, prompted by the dashboard visibly
  slowing down over a long-running session. The root causes: the desk
  was replaying its *entire* history from scratch on nearly every
  refresh, the live-trading loop was rewriting its whole audit trail to
  disk every cycle instead of just the new part, the AI's research step
  froze live trading for 8–30+ seconds every few bars, and every trading
  model recomputed its full price history on every single new bar
  instead of just the recent window it actually needs. All four are
  fixed — outputs are provably identical to before (same signals, same
  fills, same audit trail — pinned by new automated tests, not just
  "seems fine"), but a long session that used to bog down noticeably now
  stays responsive indefinitely. See `HANDOFF.md` §1h for the exact
  before/after numbers.

**Current health** (re-verified the same day as this document): **605
automated tests, 0 failing**; static type-checking and linting both clean
across all 128 source files; the license-gate scan passes for all 50
runtime dependencies.

---

## 7. The honesty math, briefly explained

Two ideas from professional quant research, translated:

- **Deflated Sharpe Ratio.** A normal "Sharpe ratio" measures return per
  unit of risk — the higher, the better the strategy looks. But if you test
  a thousand random strategies, a few will look great *purely by chance* —
  the same way if a thousand people each flip a coin ten times, someone will
  flip nine heads by luck alone. The Deflated Sharpe Ratio corrects for
  *how many things you tried* before finding this one, so a lucky fluke
  can't disguise itself as a real edge.
- **Probability of Backtest Overfitting.** This checks whether a strategy's
  good performance actually generalizes, by testing it on many different
  "did we get lucky on this exact slice of history" splits of the data, not
  just the one convenient slice that happened to look good.

A strategy has to pass **both** of these (plus a transaction-cost stress
test and simply beating "just buy and hold") before this system will ever
call it `validated`. Most simple ideas don't pass — and that's the honest,
intended result, not a bug.

---

## 8. Running it

```bash
pip install -e ".[ui,search,dev]"      # the product itself, plus dev tools
lqe doctor                              # a read-only health check
python run.py                           # opens the dashboard at 127.0.0.1
```

Windows users can just double-click `run.bat` — no terminal required.

To watch the whole 104-model catalog trade against real-time data with the
AI narrating live:
```bash
lqe live --llm --llm-model llama3.2:3b --out runs/session.jsonl
```

To verify everything from scratch (what this document's own "current
health" numbers in §6 come from):
```bash
pytest -q && ruff check . && mypy src scripts run.py && python scripts/license_gate.py
```

Full instructions for every command: `USER-GUIDE.md`.

---

## 9. Known limitations — told plainly

- **The funding/"carry" strategies are a directional proxy, not true
  market-neutral carry** (§5.3) — a real fix requires a separate decision
  about supporting short-selling, not a quick patch.
- **The 47%-flagged redundancy figure (§5.2) mixes two different causes**
  that haven't yet been fully teased apart in an automated way — some
  models really are near-duplicates worth pruning; others just happened to
  behave identically on one short test window.
- **Nothing has ever been promoted to the real "tracked" portfolio in this
  local environment** — the sample data bundled with the project is too
  small to clear the statistical bar (by design — it's a demo, not real
  history). The promotion gate has been proven correct on synthetic and
  partial data, but a real, multi-year promotion has never happened here.
- **A restart doesn't resume the AI's own research history** — only the
  actual simulated trading positions. A resumed session starts a fresh
  research campaign over the reconstructed trade history.
- **The automated test suite for the full statistics/ML library set has
  never run on a live CI server** — this repository has no remote git host
  configured, so that pipeline is validated locally but unproven on an
  actual GitHub Actions runner.
- **The autopilot's default search surface (3 models) is much narrower
  than the full catalog (104 models)** — intentional scoping from early on,
  not yet revisited.
- **Two optional sleeves were never built**: order-book/tick-level
  "microstructure" strategies and cross-exchange arbitrage research. The
  project's own plan explicitly allows deferring these past v4.0.

None of the above touch or weaken any of the 9 non-negotiable promises in
§3 — they are scope gaps and measured, disclosed shortfalls, not safety
gaps or hidden problems.

---

## 10. Where to look for more detail

| Document | What's in it | Best for |
|---|---|---|
| `README.md` | Top-level orientation + links to every spec | First stop |
| `USER-GUIDE.md` | How to run every command | Anyone actually using it |
| `COMPONENT-GUIDE.md` | Module-by-module deep dive, including known nuances and gotchas | Developers extending the code |
| `HANDOFF.md` | The terse, session-to-session engineering log — every milestone's exact evidence | Whoever picks up development next |
| `docs/00`–`14` | The original design specs + all four roadmaps (v1.0 through v4.0) | Understanding *why* something was built a certain way |
| `M12-RELEASE-REVIEW.md` / `V2-RELEASE-REVIEW.md` / `V3-RELEASE-REVIEW.md` / `V4-RELEASE-REVIEW.md` | The formal safety/honesty audit, with evidence, for each version | Verifying the promises in §3 are actually kept |
| `GUARDRAILS.md` | The hard boundary fence — what must never be done | Anyone about to make a change |
| `GLOSSARY.md` | Canonical vocabulary used throughout the project | Looking up an unfamiliar term |
| `DEVELOPER-HANDOFF.md` | A superseded (v2.0-era) snapshot, kept only for historical provenance | Understanding project history, not current state |

---

*This document was written after a full system-wide audit at v4.0 (all
tests green, a UI/UX sweep that found and fixed real inconsistencies, and a
4-phase performance overhaul with before/after numbers — see `HANDOFF.md`
for the exact diffs). It reflects the system as it actually runs today, not
as it was originally planned.*
