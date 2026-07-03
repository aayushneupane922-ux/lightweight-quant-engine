# GETTING STARTED — `lightweight-quant-engine`

Concrete day-1 steps to go from this planning package to a running Milestone 1. Assumes a solo developer using Claude Code on Windows (works on macOS/Linux too).

## 0. Prerequisites
- **Python 3.12+** (`python --version`)
- **Git** + a (free, private) GitHub repo
- **Claude Code** (Pro plan $20/mo is enough to start; see `docs/06`)
- No data account, no broker, no credentials needed. Crypto public data via `ccxt` needs no key.

## 1. Create the repo and drop in the docs
```
mkdir lightweight-quant-engine && cd lightweight-quant-engine
git init
mkdir docs
# copy all 00..23 + README.md into docs/
# copy CLAUDE.md to the repo ROOT (so Claude Code auto-loads it)
```
Put `CLAUDE.md` at the repo root. Keep the numbered specs in `docs/`.

## 2. Set up the Python environment (reference — see `REPO-SCAFFOLD.md`)
Create a virtual environment and a `pyproject.toml` with the fixed stack (ccxt, duckdb, polars, pyarrow, pandas, numpy, pandas-ta, quantstats, pydantic, nicegui, pytest, hypothesis, ruff, mypy, structlog). Exact dependency block, `.gitignore`, and folder tree are in `REPO-SCAFFOLD.md`. (Per the handoff decision, those are provided as *reference blocks to paste*, not pre-generated code files.)

```
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
```

## 3. Point Claude Code at the plan
Open the repo in Claude Code. It will load `CLAUDE.md`. Then paste the **master prompt** from `docs/17-claude-code-master-prompt.md` if you want to reinforce context, or just proceed — `CLAUDE.md` already carries the rules.

## 4. Build Milestone 1 (do this first)
Paste the **Milestone 1** block from `docs/18-claude-code-milestone-prompts.md`. It builds:
- the deterministic event core (events, clock, bus, engine, hashing),
- config with the **live-trading lockout** (schema rejects `mode: live`; `LIVE_TRADING_ENABLED=False`; `is_paper` assertion),
- the single `make_order` choke point,
- and the safety + determinism tests.

**Acceptance:** replay-equality test passes; config rejects live; `make_order` is the only `Order` constructor; hash-chain verifies; ruff + mypy clean. Then **stop and review**.

## 5. Review before moving on
Run the **safety review** (`docs/19` §19.1). Every item must PASS *with evidence* (file:line or a passing test). "I couldn't find a live path" is not a pass — demand the proving test. Only then proceed to Milestone 2.

## 6. Continue milestone by milestone
Work `docs/18` in order, one milestone per session, each ending in a review checkpoint (`docs/19`). After any change to `risk/`, `execution/`, or `paper/`, re-run the safety review before merging.

**Thin-slice option (recommended if time/motivation is tight):** do Milestones **1 → 3 → 6** first (core → backtest → minimal UI) so you have a usable system fast, then fill in 4, 5, 7, 8.

## 7. Your first data (Milestone 2)
Use `ccxt` public endpoints (no key) to pull BTC-USDT and ETH-USDT OHLCV into partitioned Parquet, then run the data-quality checks (`docs/08 §8.4`). Treat crypto results as **engineering validation**, not evidence of edge.

## 8. Before you trade anything in paper
Read `docs/09` (research protocol) and pre-commit the **kill-criteria** (`docs/09 §9.9`). A strategy may only enter paper trading after it passes the graduation checklist (`docs/09 §9.8`). No strategy is claimed to be profitable — you are testing whether it survives honest scrutiny.

## 9. Guardrails to keep in mind
- Never add anything from the "what NOT to build" list (`docs/16 §16.7`).
- Never introduce a live-order path, a credential, or a broker SDK.
- Never loosen the research kill-criteria because a backtest looks exciting.
- Re-verify any license/pricing fact before spending money (`docs/22 §22.3`).

## 10. Definition of done (every change)
ruff + mypy clean · all tests green (unit + property + parity + safety + data) · audit hash-chain verifies · license gate green · docs updated. If any is red, stop and fix — don't merge.
