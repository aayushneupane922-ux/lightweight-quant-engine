# 26 — Live Leaderboard Spec ("Many Models Racing")

This is the feature the owner most wanted: **pick several models and watch them trade the live feed side by side, in real time, simulated.** It is also the product's **highest seduction risk**, so half this spec is the honesty layer that keeps it from lying. Read §26.4 as non-negotiable.

## 26.1 What it is
A Showcase view where **N models run concurrently on one shared live public feed** (crypto, via the existing paper daemon), each with its own sub-portfolio, all routed through the **same risk gate + audit**. The UI shows a live-updating comparison (a leaderboard) and lets you drill into any single model's cockpit.

## 26.2 Engineering (reuses the existing engine)

```
           shared live feed (ccxt public WS, ONE stream)
                              │  MarketEvent fan-out
        ┌──────────────┬──────┴───────┬──────────────┐
        ▼              ▼              ▼              ▼
   Model A         Model B         Model C   …   (each a Strategy instance)
   sub-account     sub-account     sub-account     (isolated cash/positions)
        │              │              │
        └── SignalEvent ▶ sizing ▶ make_order [RISK GATE] ▶ PaperBroker (sim fills) ─┘
                              │ every event hash-chained
                              ▼
                    audit.jsonl  ─▶  StateReader  ─▶  Leaderboard UI (read-only)
```

- **One feed, many models.** Fan out each `MarketEvent` to every model instance; do **not** open N exchange connections (respect rate limits, keep determinism).
- **Isolation.** Each model has its own sub-portfolio/accounting and its own slice of a notional paper bankroll. One model's positions never touch another's.
- **Same code path.** Built via the existing `make_session` (docs: HANDOFF "parity guarantee") so a recorded race **replays deterministically** and matches backtest logic. Do not fork the session builder.
- **Concurrency.** Still single-threaded per decision step (deterministic ordering across models by (sim_ts, model_id, seq)); the daemon advances all models on each bar. No per-model threads in the decision path.

## 26.3 Kill hierarchy (safety)
- **Global KILL** stops *all* models immediately (existing persistent kill switch), cancels working orders, optional FLATTEN — unchanged.
- **Per-model halt:** a model that breaches its risk limits (or errors, or hits stale data) is **halted and flagged** individually; the others keep running. Per-model halt is logged and shown on the leaderboard.
- Per-model halt never clears itself; global kill overrides everything.

## 26.4 The honesty layer (MANDATORY — the anti-seduction rules)
A live leaderboard invites "which is winning *right now*?!" on a meaningless sample. Every one of these is required and test-enforced (`tests/honesty/`):

1. **Persistent banner:** `SIMULATED · live performance is NOT evidence of edge` — always visible on the race view, not dismissible.
2. **Sample-size first.** Each row shows **elapsed time, bars seen, and # trades** with equal or greater visual weight than P&L. A model with < the configured minimum trades shows `insufficient data`, **not** a rank.
3. **Costs applied live.** The simulated fills already include slippage + commission (docs/10); the leaderboard shows the **cost assumption** in the header and never a zero-cost number.
4. **Rank honestly.** Default sort is **not** raw live P&L. Sort by a caveated composite (e.g., risk-adjusted, sample-gated); when a model has enough data, show its **DSR / “needs out-of-sample”** state. Below threshold, rows are explicitly unranked (`observing…`).
5. **No profit framing.** No "earnings", "$ profit", "Buy/Sw" verbs, no green-is-good confetti. Neutral language: "simulated return", "unproven".
6. **Verdict chips, not hype.** Each model gets a plain-English state: `observing (n=…)`, `⚠ survives so far — validate`, `❌ negative after costs`, `★ validated (Research)`.
7. **The bridge is one click.** Every row has **▶ Send to Research** — the message being: *if it looks good live, that's a hypothesis, go prove it honestly.*
8. **Unproven ≠ validated.** Only models that passed docs/09 graduation show the `validated` badge; everything else is visibly `unproven`.

> If a stakeholder ever screenshots the leaderboard and reads it as "Model B is profitable," the honesty layer has failed. Design reviews must check exactly this.

## 26.5 Layout & interaction states
- **Leaderboard table:** row per model — name, family badge, status, **elapsed / bars / trades**, simulated return (caveated), drawdown, risk state (ok/halted), verdict chip, live equity sparkline, ▶ drill-in, ▶ Send to Research.
- **Drill-in cockpit (single model):** live price chart with signal markers, "why it traded" (the signal + risk decision from the audit), positions, running metrics, per-model kill/halt.
- **States:** **empty** ("Pick 2–5 models to start a race"); **running** (streaming updates, throttled 1–2 Hz, spinner/progress); **halted** (per-model flag); **killed** (global banner).
- **Performance:** downsample sparklines; push updates on new audit events, throttled; never block the decision loop on UI.

## 26.6 Config
```yaml
race:
  feed: {exchange: binance, symbol: BTC-USDT, timeframe: 1m}   # one shared feed
  models: [trend_ma_cross, breakout_donchian, meanrev_zscore]  # 2..5 recommended
  bankroll_each: 10000
  min_trades_for_rank: 30        # below this → 'insufficient data'
  rank_by: risk_adjusted_gated   # NOT raw_pnl
  max_bars: 5000                 # bounded session
  costs: {slippage_bps: 10, commission_bps: 25}   # shown in header
```

## 26.7 What it must never do
- Never open a real-order path or per-model broker credentials (there are none).
- Never rank on tiny samples without the `insufficient data` state.
- Never show a P&L number without sample size + cost context.
- Never imply that live out-performance = edge.
- Never exceed localhost; never add a `--host`.

## 26.8 Acceptance criteria
- ≥3 models race on one shared live feed, isolated sub-accounts, all through `make_order` + audit.
- Recorded race **replays deterministically** (same leaderboard).
- Global kill stops all; per-model halt isolates one; both audited.
- All §26.4 honesty rules present and covered by `tests/honesty/`.
- Existing `tests/safety/` still green; UI still constructs no `Order` and imports no risk/execution internals.
