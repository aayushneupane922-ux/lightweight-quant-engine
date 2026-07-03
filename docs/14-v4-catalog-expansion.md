# 14 — Catalog Expansion — Diversified +50 (v4, M23–M26)

Continuation of [`13-v3-roadmap.md`](13-v3-roadmap.md) (v3.0). Add ~50
algorithms — but the goal is **measured diversification**, not a headcount.
Same pattern as every prior roadmap: tests-first, exit gate + tag per
milestone. All the safety/honesty non-negotiables (`GUARDRAILS.md` "NEVER" /
"OUT OF SCOPE") are unchanged. Milestones are numbered **M23–M26** to
continue this project's `mN-done` tag sequence after v3's M18–M22 (the
source proposal called these `v4-M1`..`v4-M4` — mapped 1:1 below).

> **Read this first — the principle.** Diversification is **low correlation
> between models' return streams across distinct return drivers**, *not*
> the number of algorithms. 50 trend variants is one bet in 50 costumes.
> And doubling the catalog to ~100 models **doubles the multiple-testing
> surface**, so the promotion gate's trial count must grow with it or it
> will start promoting noise (§4). More models makes the gate *stricter*;
> only genuinely uncorrelated drivers make the *product* better. Sources:
> [systematic multi-strategy diversification — UBP](https://www.ubp.com/en/news-insights/newsroom/systematic-multi-strategy-as-a-portfolio-diversifier),
> [uncorrelated alpha — AllianceBernstein](https://www.alliancebernstein.com/apac/en/institutions/insights/investment-insights/the-quest-for-uncorrelated-nontraditional-returns.html),
> [crypto stat-arb/carry — IBKR/Robot Wealth](https://robotwealth.com/ideas-for-crypto-stat-arb-features/),
> [BIS crypto carry](https://www.bis.org/publ/work1087.pdf).

## 1. The diversification model (how we measure "diversified")
Group every strategy by **return-driver "sleeve."** Within a sleeve, models
are highly correlated (count as ~1 effective bet); across sleeves is where
diversification lives. The acceptance metric is a **diversification
score**, computed on held-out return streams:
- **Average pairwise correlation** of the *promoted/tracked* models
  (target: low, e.g. < ~0.3 median across sleeves).
- **Effective number of bets** (via correlation-cluster count or an
  eigenvalue/ENB measure) — the real headline, not "50 added."
- Sleeves should span **≥ 8–10 low-correlation clusters**, with **no
  single sleeve dominating** the tracked book.

## 2. The +50, by return-driver sleeve
Flags: **[spot]** = builds on existing crypto spot data · **[perp]** =
needs perpetual + funding data (new adapter, §5) · **[L2]** = needs
order-book/tick data (new adapter) · **[multi]** = needs multiple venues ·
**[gated]** = ML, extra validation · **[alloc]** = allocator (diversifies
*how* sleeves combine).

| # | Sleeve (driver) | Algorithm | Notes / lib | Data |
|---|---|---|---|---|
| A. **Trend / momentum** (cap the count — internally correlated) | | Donchian breakout (multi-TF) | own | [spot] |
| | | MA/EMA cross (exists) · MACD trend · TS-momentum (multi-lookback) · ADX-gated trend · dual (abs+relative) momentum | pandas-ta/own | [spot] |
| B. **Mean-reversion** | | Z-score · Bollinger fade · RSI fade · Keltner reversion · **Ornstein-Uhlenbeck fair-value** | own/pandas-ta | [spot] |
| C. **Cross-sectional** (rank the universe — *different driver*) | | X-sectional momentum (long top/short bottom) · X-sectional short-term reversal · X-sectional low-vol · X-sectional "value" proxy · **residual (beta-neutral) momentum** | own+pandas | [spot, multi-symbol] |
| D. **Statistical arbitrage** (*different driver*) | | Engle-Granger pairs · **Johansen basket cointegration** · distance/correlation pairs · **lead-lag (BTC→alt)** · index/basket arb | statsmodels | [spot, multi-symbol] |
| E. **Volatility** | | GARCH realized-vol regime · vol-**breakout** (expansion) · vol mean-reversion (vol-of-vol) · vol-target overlay (exists) | arch/own | [spot] |
| F. **Carry / basis** ⭐ (*structurally uncorrelated to direction — the crown-jewel diversifiers*) | | **Perp funding-rate carry** (long spot / short perp) · **cash-and-carry basis** (spot vs perp/quarterly) · funding-rate momentum/reversion · cross-exchange funding differential | own | [perp] |
| G. **Breakout / structure** | | Opening-range breakout (session) · support/resistance range · **squeeze / vol-contraction breakout** | own | [spot] |
| H. **Seasonality / calendar** (*low-correlation driver*) | | Time-of-day (hour effects) · day-of-week/weekend · turn-of-month / funding-settlement | own | [spot] |
| I. **Regime overlays** (switch sleeves, not standalone alpha) | | HMM trend/range switch · change-point (ruptures) · vol-regime gate | hmmlearn/ruptures | [spot] |
| J. **Microstructure / order-flow** | | Order-book imbalance · aggressor/trade-flow imbalance · micro-price / spread | own | [L2] |
| K. **Cross-exchange** (research/paper only — latency-sensitive) | | Cross-exchange spread · triangular arb (single venue) | ccxt | [multi] |
| L. **ML signals** [gated] (one driver, highest overfitting risk) | | LightGBM return classifier · **meta-labeling filter** (López de Prado) · logistic direction · base-signal stacking ensemble | sklearn/LightGBM | [spot] |
| M. **Allocators** [alloc] (*diversify how sleeves combine*) | | Risk parity (ERC) · **Hierarchical Risk Parity** · minimum-variance · **maximum-diversification** · inverse-vol · Black-Litterman | skfolio/riskfolio/PyPortfolioOpt | [spot] |

That's ~53 concrete strategies across **13 sleeves**. **Sleeves A, B, G are
the most internally-correlated** — cap how many of each reach the tracked
book. **Sleeves C, D, F, H are the real diversifiers** — F (carry/basis)
especially, because its returns come from funding/structure, not price
direction.

## 3. Intake gets one new step: correlation curation
Existing intake (deterministic · permissive license · manifest-complete ·
passes a backtest · `unproven` until gated) is unchanged, **plus**:
- [ ] **Redundancy check:** before a model earns a catalog slot, compute
  its return-stream correlation to existing models on held-out data. If
  it's ~redundant (high corr to something already present) **and** not
  clearly better, **quarantine it as a duplicate driver.** A diversified
  catalog rejects the 40th trend clone.
- [ ] Tag each model with its **sleeve** in the manifest so the
  diversification score and the "no sleeve dominates" rule are computable.

## 4. The trial-count consequence (do not skip)
The promotion gate's Deflated Sharpe / PBO uses the **honest count of
everything tried**. Going from 51 → ~100 models roughly doubles that count,
which **raises the bar a promoted model must clear.** This is correct and
protective — but the builder **must update the gate's trial-count to span
the full catalog × its param search**, or the bigger catalog will
manufacture false positives. Bigger catalog ⇒ stricter gate, by
construction.

## 5. Data prerequisites (be honest about what needs new plumbing)
- **No new data (build now):** A, B, C, D(pairs on spot), E, G, H, I, L, M
  — ~35 strategies on existing crypto spot (multi-symbol) data.
- **Needs perp + funding data:** **F (carry/basis)** — the highest-value
  diversifiers. Requires a small **perp/funding-rate adapter** (ccxt
  supports perp + `fetchFundingRate`) → a data prerequisite before F.
- **Needs order-book/tick data:** J (microstructure) — heavier; a new
  L2/tick adapter + storage.
- **Needs multiple venues:** K (cross-exchange) — research/paper only;
  flag latency assumptions as unrealistic in paper (do not imply this is
  tradeable edge).
- **Cross-asset honesty:** true cross-asset diversification (equity
  value/quality factors, futures term-structure carry, options vol-surface)
  needs the **equities/futures adapters (still deferred)** — don't
  overpromise it. Within crypto you can genuinely span ~10 drivers, which
  is real diversification for one asset class.

## 6. Milestone structure (v4)
- **M23 · Diversification framework + no-new-data sleeves.**
  Correlation-curation intake, the diversification score, sleeve tagging,
  and sleeves A–E, G–I, L, M (~35 strategies) on existing spot data. Update
  the gate's trial-count. Exit gate: score computed; each model passes
  intake + the (updated) gate; safety/honesty green. `git tag m23-done`.
- **M24 · Perp/funding adapter + carry/basis sleeve (F).** The
  crown-jewel diversifiers. New funding data adapter (validated like all
  data), then the 4 carry/basis strategies. Exit gate: carry/basis models
  run on real funding data, measurably low-correlation to directional
  sleeves. `git tag m24-done`.
- **M25 (optional/later) · Microstructure (J) + cross-exchange (K).**
  Only if wanted; heavier data + research-only caveats. May be deferred
  past v4.0 without blocking it — flag to the owner before starting.
- **M26 · Diversification review & tag.** Re-run validation with the full
  trial-count; report the diversification score + effective-number-of-bets;
  safety/honesty review (`V4-RELEASE-REVIEW.md`); regenerate notices;
  **tag v4.0**. (Becomes M25 if M25/microstructure is deferred — renumber
  at that point, don't leave a gap in the tag sequence.)

## 7. Acceptance gate (what "done" means — not "50 added")
- The **tracked/promoted** set spans ≥ 8–10 low-correlation sleeves with
  an acceptable diversification score (avg pairwise correlation below
  threshold; effective-number-of-bets reported), **no single sleeve
  dominating.**
- Every new model: deterministic · permissive · manifest-complete with a
  `sleeve` tag · passed correlation-curation intake · `unproven` until it
  passes the **trial-count-updated** gate.
- A deliberate weak/cautionary model remains in the catalog so the tooling
  visibly rejects something.
- Honesty layer intact everywhere; safety non-negotiables re-proven;
  license gate green.

## 8. The one-line version
Don't add 50 algorithms — add **the missing return drivers** (carry/basis,
cross-sectional, stat-arb, seasonality, microstructure) and let the
**diversification score**, not the count, define success. Cap the
trend/mean-reversion clones, prize the uncorrelated sleeves, and make the
gate stricter to match the bigger haystack.

## Sources
[UBP systematic multi-strategy](https://www.ubp.com/en/news-insights/newsroom/systematic-multi-strategy-as-a-portfolio-diversifier)
· [AllianceBernstein uncorrelated alpha](https://www.alliancebernstein.com/apac/en/institutions/insights/investment-insights/the-quest-for-uncorrelated-nontraditional-returns.html)
· [Robot Wealth crypto stat-arb](https://robotwealth.com/ideas-for-crypto-stat-arb-features/)
· [BIS crypto carry](https://www.bis.org/publ/work1087.pdf) · [Amberdata
funding-rate arbitrage](https://blog.amberdata.io/the-ultimate-guide-to-funding-rate-arbitrage-amberdata)
· awesome-quant (library sourcing).
