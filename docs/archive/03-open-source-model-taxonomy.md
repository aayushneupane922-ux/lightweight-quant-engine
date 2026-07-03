# 03 — Open-Source Quant Model Taxonomy

**Framing.** These are *model families*, not "profitable models." No family here is claimed to make money. Each entry answers: what it is, data it needs, OSS libraries, failure modes, backtest traps, **MVP / Later / Never**, how to validate rigorously, how to paper-trade safely, and whether it suits a *lightweight* engine.

**MVP model set (the only ones you should implement first):** trend-following, mean-reversion, time-series momentum, plus the supporting **execution/slippage** and **position-sizing** models. Everything else is *Later* or *Never* for the MVP. Rationale: they are deterministic, single-asset-capable, need only OHLCV, and are the easiest to validate honestly — which is the whole point.

Validation vocabulary used below is defined in [`09-backtesting-research-protocol.md`](09-backtesting-research-protocol.md): walk-forward, purged/embargoed CV, Deflated Sharpe Ratio (DSR), Probability of Backtest Overfitting (PBO), turnover/capacity, ablation.

---

## A. Directional / signal families

### 1. Trend-following — **MVP**
- **What:** enter in the direction of an established move (MA crossovers, Donchian channel breakouts, MACD). Convex payoff: many small losses, few large wins.
- **Data:** OHLCV bars only. Works at any timeframe.
- **OSS:** `pandas-ta` (MA/MACD/ADX), your own Donchian; analytics via `QuantStats`.
- **Failure modes:** whipsaw in ranging markets; large give-back at reversals; performance concentrated in a few regime windows.
- **Backtest traps:** signal computed on the **close** but filled at that same close (look-ahead); ignoring costs on a high-turnover variant; fitting the lookback to one asset/one period.
- **Validate:** walk-forward across regimes; parameter-sensitivity heatmap (edge should be a *plateau*, not a spike); DSR after counting every parameter tried.
- **Paper-trade safely:** bar-close decisions only; cap position; daily-loss limit; confirm the *live* signal equals the *replayed* signal bit-for-bit.
- **Lightweight fit:** excellent.

### 2. Mean-reversion — **MVP**
- **What:** fade deviations from a reference (z-score of price vs. moving average, Bollinger reversion, RSI extremes). Concave payoff: many small wins, occasional large loss.
- **Data:** OHLCV. Prefers liquid, range-bound instruments.
- **OSS:** `pandas-ta` (Bollinger/RSI), `statsmodels` (rolling stats), `numpy`.
- **Failure modes:** **catastrophic in trends/regime breaks** ("picking up pennies in front of a steamroller"); fat left tail.
- **Backtest traps:** survivorship (delisted/depegged assets removed); assuming you get filled at the exact reversion price; ignoring that spreads widen exactly when you'd fade.
- **Validate:** stress-test through trend regimes and crash windows; enforce a hard stop and measure worst-case, not just average; DSR/PBO.
- **Paper-trade safely:** mandatory stop-loss + max-position; monitor tail P&L, not mean; kill on daily-loss breach.
- **Lightweight fit:** excellent (single asset).

### 3. Momentum (time-series / absolute) — **MVP**
- **What:** an asset that has risen over lookback *N* tends to continue over horizon *H* (time-series momentum). Distinct from cross-sectional momentum.
- **Data:** OHLCV; longer history for lookback stability.
- **OSS:** trivial with `pandas`/`numpy`; `QuantStats` for analysis.
- **Failure modes:** momentum crashes (sharp reversals after stress); sensitive to lookback/rebalance choices.
- **Backtest traps:** overlapping-return look-ahead; rebalance timing assumptions; ignoring turnover cost.
- **Validate:** multiple lookback/horizon pairs must *all* be reasonable (robustness), not one lucky pair; walk-forward; cost sensitivity.
- **Paper-trade safely:** low turnover, scheduled rebalances, position caps.
- **Lightweight fit:** excellent.

### 4. Cross-sectional factor models — **Later**
- **What:** rank a *universe* by factors (value, quality, momentum, size, carry) and go long top / short bottom.
- **Data:** a **universe** of instruments + (often) fundamentals; point-in-time data to avoid look-ahead. Much heavier than single-asset OHLCV.
- **OSS:** `Qlib`, `zipline-reloaded` + `alphalens-reloaded`, `skfolio` for allocation.
- **Failure modes:** factor decay/crowding; look-ahead via restated fundamentals; needs many names to diversify idiosyncratic risk.
- **Backtest traps:** survivorship, point-in-time fundamentals, and universe-construction bias are severe here.
- **Validate:** alphalens-style IC/quantile analysis; strict point-in-time data; walk-forward.
- **Paper-trade safely:** needs a real universe + reliable data → **not MVP**; revisit after equities data is solved.
- **Lightweight fit:** poor (needs universe + fundamentals). **Later.**

### 5. Pairs / statistical arbitrage — **Later**
- **What:** trade the spread between cointegrated instruments, betting on mean-reversion of the spread.
- **Data:** ≥2 aligned price series; enough history to test cointegration stability.
- **OSS:** `statsmodels` (Engle-Granger/Johansen, ADF), `arch` (spread vol).
- **Failure modes:** **cointegration breaks** (the pair de-couples and the spread trends against you); the classic silent-killer strategy.
- **Backtest traps:** in-sample cointegration that vanishes out-of-sample; multiple-testing across all pair combinations (huge PBO risk); look-ahead in hedge-ratio estimation.
- **Validate:** out-of-sample cointegration re-tests; rolling hedge ratios; count *every* pair tested for DSR; hard spread stop.
- **Paper-trade safely:** needs two simultaneous instrument feeds + careful accounting → **not MVP** (do it after multi-instrument support is solid).
- **Lightweight fit:** moderate. **Later.**

### 6. Breakout — **MVP (as a trend variant)**
- **What:** enter when price clears a defined level (range high/low, Donchian, prior day's range).
- **Data:** OHLCV. **OSS:** trivial + `pandas-ta`.
- **Failure modes:** false breakouts (mean-reversion regimes); slippage worst exactly at breakout.
- **Backtest traps:** intrabar fill assumptions (did you *really* get filled at the level, or gap through it?); look-ahead using the bar that confirmed the breakout.
- **Validate:** model realistic breakout slippage; walk-forward.
- **Paper-trade safely:** conservative fill model; position caps.
- **Lightweight fit:** excellent. Implement alongside trend-following.

---

## B. Statistical / structural families

### 7. Volatility models (GARCH family) — **Later (as an input, not a standalone strategy)**
- **What:** model/forecast conditional volatility (ARCH/GARCH/EGARCH) for sizing, filtering, or vol-targeting.
- **Data:** returns series. **OSS:** `arch` (bashtage). ([arch](https://github.com/bashtage/arch))
- **Failure modes:** vol forecasts are decent; *directional* bets built on them are not implied. Misused as an alpha source.
- **Backtest traps:** using full-sample-fit vol; leaking future vol into sizing.
- **Validate:** out-of-sample vol forecast error; use it as a *filter/sizer* and ablate it (does it actually help?).
- **Paper-trade safely:** only as a sizing/regime input to an MVP strategy, gated by risk engine.
- **Lightweight fit:** good as an *input module*. **Later.**

### 8. Market-regime detection — **Later (as an overlay/filter)**
- **What:** classify the market into states (trend/range, low/high vol) to switch or gate strategies. Methods: HMM, change-point detection, simple vol/trend filters.
- **Data:** returns/vol features. **OSS:** `hmmlearn` (HMM), `ruptures` (change-point), `statsmodels` (Markov-switching).
- **Failure modes:** regimes are labeled *after the fact*; models are unstable and easy to overfit; "regime" often just re-expresses a moving-average filter.
- **Backtest traps:** fitting regimes in-sample then "discovering" they predict returns; look-ahead in state assignment.
- **Validate:** strictly causal (state at *t* uses only data ≤ *t*); ablate against a trivial vol filter — if a 1-line filter does as well, prefer it.
- **Paper-trade safely:** as an on/off overlay for MVP strategies, never as a black-box driver.
- **Lightweight fit:** moderate; start with a *trivial* regime filter, not HMM. **Later.**

## C. Portfolio / allocation families

### 9. Portfolio optimization (mean-variance / Black-Litterman) — **Later**
- **What:** choose weights across assets to trade off expected return vs. risk (Markowitz MVO; Black-Litterman blends views with equilibrium).
- **Data:** returns covariance; BL needs a prior + views. **OSS:** `PyPortfolioOpt`, `skfolio`, `riskfolio-lib`.
- **Failure modes:** MVO is notoriously **unstable** (error-maximizing: tiny input changes → wild weight swings); estimation error dominates.
- **Backtest traps:** in-sample covariance; ignoring turnover/costs of rebalancing.
- **Validate:** out-of-sample; shrinkage/robust covariance; compare against equal-weight (a brutal, honest benchmark).
- **Lightweight fit:** fine as a *later* allocation layer over ≥3 MVP strategies. **MVP uses fixed-fractional / vol-targeting instead.**

### 10. Risk parity — **Later**
- **What:** size positions so each contributes equal risk.
- **OSS:** `riskfolio-lib`, `skfolio`. **Failure modes:** leverage sensitivity; correlation-regime shifts; needs decent covariance.
- **Verdict:** **Later**, once you have multiple uncorrelated strategies/assets.

### 11. Hierarchical Risk Parity (HRP) — **Later**
- **What:** López de Prado's clustering-based allocation; avoids inverting an unstable covariance matrix; often more robust out-of-sample than MVO.
- **OSS:** `skfolio` (native), `PyPortfolioOpt` (`HRPOpt`), `riskfolio-lib`.
- **Verdict:** **Later** — the preferred allocator when you reach the portfolio layer, precisely because it's less overfit-prone than MVO.

### 12. Black-Litterman — **Later** (covered in #9). Nice for *incorporating views* without MVO's instability, but adds complexity you don't need in MVP.

## D. Machine-learning families

### 13. Supervised ML signal models / tree-based — **Later (and cautiously)**
- **What:** predict next-period return/direction from features (LightGBM/XGBoost/sklearn).
- **Data:** engineered features + labels; lots of care on leakage. **OSS:** `scikit-learn`, `lightgbm`, `Qlib`.
- **Failure modes / traps:** **the overfitting epicenter** — feature leakage, non-stationary targets, label look-ahead, and multiple-testing across features/hyperparameters. A solo dev with a fast trainer will produce beautiful, fake backtests.
- **Validate:** purged & embargoed cross-validation (López de Prado); DSR/PBO with an honest trial count; feature-importance stability; brutal out-of-sample test.
- **Verdict:** **Later — only after** data integrity, backtest discipline, and paper-trading infra are proven. Tree-based first (interpretable); no deep learning in MVP.

### 14. Time-series forecasting (ARIMA/Prophet/deep) — **Later / rarely as primary**
- **What:** forecast the price/return series directly.
- **Failure modes:** price series are near-random-walk; point forecasts rarely beat naive; deep models overfit.
- **Verdict:** **Later**, and generally as an *input/feature*, not a standalone trading rule.

### 15. Reinforcement learning — **Never (for MVP)**
- **What:** learn a trading policy via reward (FinRL, TensorTrade).
- **Failure modes:** non-deterministic training, extreme overfitting, unstable, near-impossible to validate honestly for a solo dev; conflicts with your constraints (deterministic, testable, no autonomous opaque decisions).
- **Verdict:** **Never for MVP.** Optional far-future research spike, with heavy skepticism.

## E. Microstructure / mechanics families (support models — belong in MVP)

### 16. Execution / slippage models — **MVP**
- **What:** how a paper order becomes a fill: next-bar-open fill, spread/slippage assumptions, partial fills, latency.
- **Why MVP:** without a *conservative* fill model your backtest and paper trading lie to you.
- **OSS:** your own, informed by exchange spread/volume; ccxt for live spread reference.
- **Validate:** compare fill assumptions to realized paper fills; sensitivity of results to slippage (edge that dies under realistic costs isn't an edge).
- **See:** [`10-paper-trading-engine-spec.md`](10-paper-trading-engine-spec.md) §Fill simulator.

### 17. Position-sizing / money-management models — **MVP**
- **What:** how much to trade: fixed-fractional, volatility targeting, **fractional (capped) Kelly**, max-position caps.
- **Why MVP:** sizing dominates path risk; it's a first-class safety control, enforced by the risk engine.
- **Failure modes:** full Kelly is far too aggressive; sizing on in-sample vol; ignoring correlation.
- **Verdict:** **MVP** — implement fixed-fractional + vol-targeting first; Kelly only fractional and capped.
- **See:** [`11-risk-engine-spec.md`](11-risk-engine-spec.md).

---

## 3.x MVP vs Later vs Never — at a glance

| Family | MVP | Later | Never (MVP) |
|---|:--:|:--:|:--:|
| Trend-following | ✅ | | |
| Mean-reversion | ✅ | | |
| Time-series momentum | ✅ | | |
| Breakout | ✅ | | |
| Execution/slippage | ✅ | | |
| Position-sizing | ✅ | | |
| Cross-sectional factor | | ✅ | |
| Pairs / stat-arb | | ✅ | |
| Volatility (GARCH) input | | ✅ | |
| Regime detection | | ✅ | |
| Portfolio opt / RP / HRP / BL | | ✅ | |
| Supervised ML / trees | | ✅ | |
| Time-series forecasting | | ✅ | |
| Reinforcement learning | | | ✅ |

**Discipline rule that overrides everything:** a model is only allowed into paper trading after it passes the graduation checklist in [`09`](09-backtesting-research-protocol.md). Implementing a family is easy; *validating* it honestly is the hard, valuable work.
