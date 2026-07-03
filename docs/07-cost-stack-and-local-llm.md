# 07 — Cost, Stack & Local LLM (FINAL)

Still a **~$0/month** system to run. The autonomy + LLM + 3D additions stay free because they run locally. Deep cost breakdown: [`archive/06-cost-analysis.md`](archive/06-cost-analysis.md).

## 7.1 Cost table (what's free, what isn't)
| Item | Choice | Cost | Note |
|---|---|---|---|
| Engine, GUI, 3D viz, storage | local (Python, NiceGUI, three.js, DuckDB/Parquet) | **$0** | runs on your machine |
| Market data (crypto) | ccxt public endpoints | **$0** | no key; research/paper only |
| Learning loop (Optuna, sklearn, LightGBM, River) | local | **$0** | CPU fine at this scale |
| **Local LLM** (Ollama) | local inference | **$0** | needs adequate RAM/GPU (§7.3) |
| Build labor | Claude Code (Pro $20 / Max $100–$200) | subscription | your only recurring cost |
| Compute for heavy autonomous search | your CPU/GPU (or a rented GPU hour, optional) | $0–small | only if you want faster sweeps |

**Bottom line:** non-Claude spend ≈ **$0/month**. The autopilot's aggressiveness is bounded by *your local compute*, not a bill.

## 7.2 Stack (final)
Python 3.12+ · ccxt · duckdb+polars+pyarrow · pandas/numpy · pandas-ta · statsmodels/arch/hmmlearn/ruptures · skfolio/PyPortfolioOpt/riskfolio-lib · scikit-learn/LightGBM/River/**Optuna** · pydantic · FastAPI+NiceGUI · three.js+`3d-force-graph` · **Ollama** (optional) · pytest+hypothesis · ruff+mypy · structlog. All MIT/BSD/Apache/NCSA (permissive) except the optional local LLM weights (check each model's license — Llama/Qwen/Mistral community licenses permit local research use; verify before any distribution).

## 7.3 Local LLM — feasibility & role
- **Feasibility (2026):** Ollama runs a 7–8B model (Llama 3.1 8B / Qwen 3 8B / Mistral) at Q4 on **~16GB RAM or an 8–12GB-VRAM GPU** at 40+ tok/s; 8GB RAM is the CPU-only floor; 24–32GB VRAM enables 13–32B for better reasoning. ([Ollama system requirements 2026](https://localaimaster.com/blog/ollama-system-requirements))
- **Role (see [`02`](02-autonomy-autopilot-and-learning-loop.md) §2.6):** orchestrator reasoning + narration, emitting **structured tool calls** (propose_space, run_trials, promote_if_valid, de_risk, narrate). Low temperature for the control loop; prompt+response logged for replay. **Never** the numerical optimizer (that's Optuna) and **never** the validator.
- **Optional:** a rule-based orchestrator runs the same loop without any LLM — start there, add the LLM for smarter hypotheses + better narration.
- **Recommendation:** begin with a local 7–8B model; only consider a larger/hosted model if hypothesis quality is limiting — but note more LLM ≠ better trading outcomes; the gate ([`04`](04-validation-and-overfitting-protocol.md)) governs quality, not the model size.

## 7.4 When money would enter (deferred triggers)
Faster autonomous search (rented GPU hours), reliable equities/futures data (paid feed), or distribution (code-signing + license/LLM-weights review). None needed for the MVP. Verify before spending: [`09`](09-decision-log-risks-open-questions.md) §"verify before spending."
