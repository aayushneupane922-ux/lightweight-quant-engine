# 15 — Open-Source License Review

> **Engineering reading, not legal advice.** If you ever *distribute* a Windows `.exe` commercially, have a lawyer confirm this analysis (see [`14`](14-safety-risk-and-compliance-review.md) §14.12). Two usage scenarios matter and differ: **(P) Private use** — you run it on your own machine, distribute nothing; almost every license is permissive here. **(D) Distribution** — you ship the app to others; copyleft (GPL/LGPL) and Commons Clause now matter.

## 15.1 License table (verified July 2026)

| Dependency | License | Copyleft? | Private use (P) | Distribution (D) | Verdict |
|---|---|---|---|---|---|
| Your engine | your choice (MIT/proprietary) | — | ✅ | ✅ | — |
| **ccxt** | MIT | no | ✅ | ✅ | **USE** ([repo](https://github.com/ccxt/ccxt)) |
| DuckDB | MIT | no | ✅ | ✅ | USE |
| Polars | MIT | no | ✅ | ✅ | USE |
| PyArrow | Apache-2.0 | no | ✅ | ✅ | USE |
| pandas | BSD-3 | no | ✅ | ✅ | USE |
| NumPy | BSD-3 | no | ✅ | ✅ | USE |
| Numba | BSD-2 | no | ✅ | ✅ | USE |
| pandas-ta | MIT | no | ✅ | ✅ | USE |
| TA-Lib (python) | BSD-3 | no | ✅ | ✅ | USE (optional; C build) |
| QuantStats | Apache-2.0 | no | ✅ | ✅ | USE ([repo](https://github.com/ranaroussi/quantstats)) |
| empyrical(-reloaded) | Apache-2.0 | no | ✅ | ✅ | USE |
| skfolio | BSD-3 | no | ✅ | ✅ | USE ([repo](https://github.com/skfolio/skfolio)) |
| PyPortfolioOpt | MIT | no | ✅ | ✅ | USE |
| riskfolio-lib | BSD-3 | no | ✅ | ✅ | USE |
| statsmodels | BSD-3 | no | ✅ | ✅ | USE |
| arch | NCSA (permissive) | no | ✅ | ✅ | USE ([repo](https://github.com/bashtage/arch)) |
| hmmlearn | BSD-3 | no | ✅ | ✅ | USE |
| ruptures | BSD-2 | no | ✅ | ✅ | USE |
| NiceGUI | MIT | no | ✅ | ✅ | USE ([nicegui.io](https://nicegui.io)) |
| Streamlit | Apache-2.0 | no | ✅ | ✅ | USE (secondary) |
| pywebview | BSD-3 | no | ✅ | ✅ | USE (packaging) |
| PyTauri | MIT + Apache-2.0 | no | ✅ | ✅ | USE (packaging) |
| pydantic | MIT | no | ✅ | ✅ | USE |
| pytest / hypothesis | MIT / (BSD-like) | no | ✅ | ✅ | USE (dev) |
| **QuantConnect LEAN** | Apache-2.0 | no | ✅ | ✅ | LEARN / future adapter ([LICENSE](https://github.com/QuantConnect/Lean/blob/master/LICENSE)) |
| **NautilusTrader** | **LGPL-3.0** | **weak** | ✅ | ⚠️ **handle deliberately** | LEARN / future engine ([licensing](https://nautilustrader.io/legal/open-source-licensing/)) |
| **Backtrader** | **GPL-3.0** | **strong** | ✅ | ⛔ **avoid** | **AVOID** (also unmaintained) |
| **vectorbt (open)** | **Apache-2.0 + Commons Clause** | no (but **sale-restricted**) | ✅ | ⚠️ **research only** | **RESEARCH ONLY** ([license](https://vectorbt.dev/terms/license/)) |
| vectorbt PRO | commercial (~$20/mo) | n/a | paid | paid | optional, out of scope |

## 15.2 The three licenses that actually constrain you

### Backtrader — GPL-3.0 (strong copyleft) → **AVOID**
GPL-3.0 requires that if you distribute a work that includes/derives from GPL code, the *entire combined work* be offered under GPL-3.0 (source included). For a Windows app you might want to keep closed or under your own terms, that's a hard conflict. Combined with its unmaintained status, there is no reason to touch it. If you ever want its *ideas*, read the code; don't depend on it.

### NautilusTrader — LGPL-3.0 (weak copyleft) → **handle deliberately**
LGPL generally lets you use the library in a larger (even closed) application **if you link to it as a separate component** and allow users to replace/relink that component; **modifications to Nautilus itself** must be shared under LGPL. Python's import model is usually treated as dynamic linking, so *using* Nautilus unmodified in your app is typically fine, but **shipping a bundled `.exe`** (frozen/embedded) muddies the "user can relink" requirement. **Recommendation:** keep Nautilus behind an adapter, don't fork/modify it, and get a legal read before distributing any bundle that embeds it. ([Nautilus licensing](https://nautilustrader.io/legal/open-source-licensing/)) This is a *future* concern — it's not in the MVP runtime.

### vectorbt (open) — Apache-2.0 **+ Commons Clause** → **research only**
The Commons Clause overlays Apache-2.0 to forbid **selling** a product/service whose value is *primarily* the software. Private research is fine; making it the engine of a product you distribute/sell is exactly what the clause targets. **Recommendation:** use it offline for hypothesis screening; keep it out of the shipped runtime; re-validate anything it finds in your own engine. ([license](https://vectorbt.dev/terms/license/))

## 15.3 Distribution scenario: shipping a Windows `.exe`

If/when you package the app for others:
- **Clean:** everything in the MVP runtime (ccxt, DuckDB, Polars, pandas-ta, QuantStats, NiceGUI, pydantic, skfolio, statsmodels, arch, hmmlearn, ruptures, pywebview, PyTauri) is MIT/BSD/Apache-2.0 — permissive, distributable, just preserve notices.
- **Attribution:** bundle a `THIRD_PARTY_NOTICES` file listing each dependency + its license text (Apache-2.0 §4 and BSD/MIT require notice preservation).
- **Avoid in the bundle:** Backtrader (GPL), vectorbt (Commons Clause). Nautilus (LGPL) only with the relinking caveat + legal review.
- **Apache-2.0 patent grant** (LEAN, QuantStats, PyArrow, Streamlit, NiceGUI-adjacent) is a plus for distribution.
- **Your own code:** pick MIT (permissive) or keep proprietary — your call; nothing in the runtime forces copyleft.

## 15.4 Dependency-risk notes

- **Commons Clause creep:** watch for other libraries adopting Commons Clause or "BSL/SSPL"-style source-available licenses; they can restrict commercial/distribution use. Re-check licenses at each dependency bump.
- **Maintenance risk ≠ license risk but compounds it:** empyrical/pandas-ta originals had gaps → prefer the maintained forks (`empyrical-reloaded`, `pandas-ta-classic`) behind your interface so a swap is trivial.
- **Transitive licenses:** run a license scan (`pip-licenses`) in CI and fail the build on GPL/Commons-Clause creeping into the runtime dependency tree.

## 15.5 Recommendations (summary)

1. **Runtime = permissive only** (MIT/BSD/Apache-2.0). ✅ satisfied by the recommended stack.
2. **Backtrader:** avoid entirely.
3. **vectorbt:** research-only, never in the shipped runtime.
4. **NautilusTrader:** adapter-only, unmodified, legal review before distributing a bundle.
5. **Add CI license gate** (`pip-licenses`) to block copyleft/Commons-Clause in runtime deps.
6. **Ship `THIRD_PARTY_NOTICES`** if you distribute.
7. **Get professional review** before any commercial distribution or before embedding LGPL code in a `.exe`.

*License facts change; re-verify at [`23-appendix-source-map.md`](23-appendix-source-map.md) sources before relying on this for distribution.*
