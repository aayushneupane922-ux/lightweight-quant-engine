# REPO SCAFFOLD (reference) — `lightweight-quant-engine`

Copy-pasteable reference blocks for the repository skeleton. **Per the handoff decision, these are provided as reference to paste, not as pre-generated code files.** Claude Code will create the real files during Milestone 1.

## Folder tree
```
lightweight-quant-engine/
├── CLAUDE.md
├── HANDOFF.md
├── GETTING-STARTED.md
├── REPO-SCAFFOLD.md
├── README.md
├── pyproject.toml
├── .gitignore
├── THIRD_PARTY_NOTICES.md          # generated at Milestone 9
├── docs/                            # 00..23 spec files
├── config/
│   ├── engine.example.yaml
│   └── risk.example.yaml
├── src/lqe/
│   ├── __init__.py
│   ├── constants.py                 # LIVE_TRADING_ENABLED = False
│   ├── core/        # events, clock, bus, engine, context, determinism
│   ├── data/        # base, ccxt_adapter, csv_replay, ingest, validate, symbols
│   ├── storage/     # parquet, catalog, replay_bundle
│   ├── strategies/  # base, trend_ma_cross, mean_reversion_z, ts_momentum
│   ├── models/      # base (+ later plugins)
│   ├── portfolio/   # accounting, sizing
│   ├── risk/        # engine, rules
│   ├── execution/   # base, paper_broker, fills, slippage, commission, _locked_out
│   ├── analytics/   # metrics, report
│   ├── backtest/    # runner
│   ├── paper/       # daemon, control, kill_switch
│   ├── ui/          # app, views/
│   └── cli.py
├── tests/
│   ├── unit/  integration/  property/  parity/  safety/  data/
└── research/
    ├── journal/     # H-YYYYMMDD-nn.md hypotheses
    └── notebooks/
```

## `pyproject.toml` (reference dependency set — pin versions at install time)
```toml
[project]
name = "lightweight-quant-engine"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
  "ccxt",            # MIT — crypto market data (public endpoints only)
  "duckdb",          # MIT — local OLAP over Parquet
  "polars",          # MIT — fast dataframes
  "pyarrow",         # Apache-2.0 — Parquet/Arrow
  "pandas",          # BSD-3
  "numpy",           # BSD-3
  "pandas-ta",       # MIT — indicators (or pandas-ta-classic)
  "quantstats",      # Apache-2.0 — analytics/tearsheets (or quantstats-reloaded)
  "pydantic",        # MIT — config/schema validation
  "nicegui",         # MIT — local UI
  "structlog",       # Apache-2.0/MIT — structured audit logging
]

[project.optional-dependencies]
dev = ["pytest", "hypothesis", "ruff", "mypy", "pip-licenses"]
# LATER (post-MVP, keep out of runtime until needed):
#   skfolio (BSD-3), PyPortfolioOpt (MIT), riskfolio-lib (BSD-3),
#   statsmodels (BSD-3), arch (NCSA), hmmlearn (BSD-3), ruptures (BSD-2),
#   pywebview (BSD-3), pytauri (MIT+Apache-2.0)

[project.scripts]
lqe = "lqe.cli:main"

[tool.ruff]
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]
```
> **License gate:** everything above is MIT/BSD/Apache-2.0/NCSA (permissive). **Never** add GPL (Backtrader) or Commons-Clause (`vectorbt`) to the runtime. `vectorbt`, if used at all, is offline-research only and must not be imported by `src/lqe/**`. Add a CI step running `pip-licenses` that fails on GPL/Commons-Clause in runtime deps (Milestone 9).

## `.gitignore` (reference)
```
.venv/
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.pytest_cache/
# local data & run artifacts (never commit market data or audit logs)
data/
runs/
*.duckdb
*.parquet
*.jsonl
# secrets — there are NONE in the MVP; keep it that way
.env
*.key
```

## `constants.py` (the compile-time lockout — reference)
```python
# The MVP is paper-only. There is no supported way to enable live trading.
LIVE_TRADING_ENABLED: bool = False

# Enforced elsewhere:
#  - config Enums exclude mode: live and real execution adapters (pydantic)
#  - engine startup asserts execution_adapter.is_paper is True
#  - the only ExecutionAdapter implementation is PaperBroker
#  - CI safety tests forbid broker SDK imports and ccxt order-creation calls
```

## Suggested CI (GitHub Actions — reference outline)
```
on: [push, pull_request]
jobs:
  check:
    steps:
      - ruff check .
      - mypy src
      - pytest            # unit + property + parity + safety + data
      - pip-licenses --fail-on 'GPL;Commons Clause'   # runtime deps only
```

## Notes
- Real files are created by Claude Code at Milestone 1 (`docs/18`), not here.
- Keep `data/`, `runs/`, and `*.duckdb`/`*.jsonl` out of git — they can be large and may carry data under exchange ToS (keep local).
- Version pins: pin exact versions at install time and re-check licenses (`docs/15`, `docs/23`) since they drift.
