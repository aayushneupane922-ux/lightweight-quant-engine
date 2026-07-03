# 25 — Model Catalog Spec

The catalog is what turns "one example strategy" into the **library of models** you wanted. Each entry is a plugin behind the *existing* interfaces (`Strategy` / `Model`, docs/12) — no new engine capability, just more models + a manifest that makes each one legible in the Showcase.

## 25.1 Catalog entry = plugin + manifest

Every model ships a **manifest** (surfaced on its Showcase card and in Research):

```yaml
id: trend_ma_cross
name: "Moving-Average Trend (MA cross)"
family: trend            # trend | mean_reversion | pairs | portfolio | factor
one_liner: "Buy when the fast average crosses above the slow one; exit on cross-down."
economic_rationale: "Persistent order flow / underreaction can make moves autocorrelate."
data_needs: {instruments: 1, kind: OHLCV, min_history: "2y multi-regime"}
oss_libs: ["pandas-ta"]
params_schema: {fast: int>0, slow: int>fast}
failure_modes: ["whipsaw in ranging markets", "give-back at reversals"]
validation: {min_trades: 200, needs: [walk_forward, cost_sweep, dsr]}
wave: A
status: unproven         # unproven | in_research | validated  (set by Research, not by author)
single_asset: true
```

The manifest fields map 1:1 to docs/03 (family, rationale, data, failure modes, validation) and to docs/09 (validation gates). **Authors never set `status: validated`** — only a passing Research graduation run does (docs/09 §9.8).

## 25.2 The catalog (all four families, staged by wave)

### Family 1 — Trend / Momentum / Breakout  (Wave A · single-asset · OHLCV)
| id | model | OSS | params | key failure mode |
|---|---|---|---|---|
| `trend_ma_cross` | MA crossover (exists) | pandas-ta | fast, slow | whipsaw |
| `trend_macd` | MACD trend | pandas-ta | fast, slow, signal | lag at turns |
| `breakout_donchian` | Donchian channel breakout | own | lookback | false breakouts |
| `momentum_tsmom` | time-series momentum | own | lookback, hold | momentum crashes |
| `trend_adx_filter` | trend + ADX strength gate | pandas-ta | period, thr | flat in chop |

### Family 2 — Mean-Reversion / Pairs  (Wave A single-asset · Wave C pairs)
| id | model | OSS | wave | key failure mode |
|---|---|---|---|---|
| `meanrev_zscore` | price z-score reversion | numpy/pandas | A | trends = large loss |
| `meanrev_bollinger` | Bollinger-band reversion | pandas-ta | A | regime break |
| `meanrev_rsi` | RSI extreme fade | pandas-ta | A | persists in trend |
| `pairs_coint` | cointegration spread (stat-arb) | statsmodels | **C** | cointegration breaks |

### Family 3 — Volatility-targeting / Risk-parity / HRP  (Wave B · portfolio · multi-asset basket)
| id | model | OSS | wave | notes |
|---|---|---|---|---|
| `vol_target` | scale exposure to target vol | arch / own EWMA (exists: `EwmaVolModel`) | B | sizing overlay, ablation-tested |
| `risk_parity` | equal risk contribution | riskfolio-lib | B | needs covariance; leverage-sensitive |
| `hrp` | hierarchical risk parity | skfolio / PyPortfolioOpt | B | more robust than MVO; clustering-based |
| `mvo` | mean-variance (baseline, unstable) | PyPortfolioOpt | B | error-maximizer; include as cautionary baseline |

### Family 4 — Factor / Multi-asset  (Wave C · basket + ranking · heaviest data)
| id | model | OSS | wave | notes |
|---|---|---|---|---|
| `factor_xsec_momentum` | cross-sectional momentum rank | own + pandas | C | crowding/decay |
| `factor_lowvol` | low-volatility rank | own | C | regime-sensitive |
| `factor_carry` | carry rank (funding, if perps) | own | C | needs funding data (later) |

## 25.3 How entries render

- **Showcase card:** name, family badge, one-liner, rationale, data needs, failure modes, **status badge** (unproven/in-research/validated), and buttons: **▶ Add to Race**, **▶ Send to Research**.
- **Research view:** the existing bench (docs/13) — backtest, cost sweep, DSR/PBO, ablation, kill-criteria — bound to the selected model.
- **Never** show a card with a P&L number and no context; every performance figure carries its sample size + cost assumption + "simulated" tag (docs/26 §26.4).

## 25.4 Mapping to existing code
- Directional & mean-reversion single-asset models → `src/lqe/strategies/` (like `trend_ma_cross`).
- Portfolio & factor models → combine a `Model` (allocation/ranking, `src/lqe/models/`) feeding a thin `Strategy` that turns weights/ranks into `SignalEvent`s. Reuse `EwmaVolModel` as the pattern.
- All emit `SignalEvent`s only → sizing → **`make_order` risk gate** → `PaperBroker`. **No model constructs an `Order`.**
- Each model = one file + one manifest + tests (unit + a Research validation run). Register via the existing plugin discovery.

## 25.5 Data implications (why the waves exist)
- **Wave A** models need **one instrument, OHLCV** — already fully supported.
- **Wave B** needs a **basket** (≥3 instruments) with aligned bars + covariance → add multi-symbol session accounting.
- **Wave C** needs **multi-instrument alignment** (pairs) and/or a **ranked universe** with survivorship-safe history → the heaviest data plumbing; do last. Factor/carry may need funding-rate data (a later crypto data type, docs/08).

## 25.6 Validation rules specific to the catalog
- A model may be **shown live** (observation) at any wave, clearly marked `unproven`.
- A model may be **ranked as validated** only after a Research graduation run (docs/09 §9.8): walk-forward OOS, cost-survival, DSR>0, acceptable PBO, beats random-entry/equal-weight.
- **Pairs and factor models get extra scrutiny** (multiple-testing across pairs/factors inflates PBO — count every combination tried; docs/09 §9.7).
- The catalog must include **at least one deliberately weak/cautionary model** (e.g., `mvo` or an over-fit-prone parameter set) so users *see* the honesty tooling reject something. Teaching the kill is a feature.

## 25.7 Non-goals (still)
No RL/LLM decision models; no deep learning; no options; no order-book/HFT; no live trading. New models must be **deterministic** and testable (docs/09, CLAUDE.md rule 4). If a proposed model can't be validated honestly offline, it doesn't enter the catalog.
