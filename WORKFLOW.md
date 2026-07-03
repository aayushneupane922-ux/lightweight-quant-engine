# WORKFLOW — How to Build This (per change, per milestone)

Solo builder driving Claude Code. One milestone per focused session. Follow this loop every time; it keeps the work disciplined and reversible.

## The per-milestone loop
1. **Pick the milestone** from `docs/10` (in order). Don't start the next until the current **exit gate** is green.
2. **Read the relevant docs** for it (`docs/10` lists them; contracts in `docs/11`). Re-read `GUARDRAILS.md`.
3. **Write the tests first** where practical — especially `tests/safety` and `tests/honesty` for anything touching risk/execution/autonomy/UI.
4. **Implement** the smallest thing that passes, behind the interfaces in `docs/11`. No scope beyond the milestone.
5. **Run the full suite + review**: `pytest`, `ruff`, `mypy --strict`, `scripts/license_gate.py`, plus the safety review (`docs/archive/19` §19.1) and the honesty checklist.
6. **Self-check against `GUARDRAILS.md`** — did anything drift, expose a port, add a dep, or weaken a gate?
7. **Commit + tag**: `git commit` then `git tag mN-done`. This is your rollback point.
8. **STOP for human review** before the next milestone.

## Definition of done (every change — all must be true)
- [ ] `ruff` clean · `mypy --strict` clean
- [ ] All tests green: unit + property + parity + safety + honesty (+ data/integration where relevant)
- [ ] Audit hash-chain verifies; determinism/replay holds
- [ ] `PromotionGate` un-bypassable; only `Validator` sets `validated`
- [ ] GUI renders no CLI/stdout; sandbox ≠ tracked never conflated
- [ ] `127.0.0.1` only; no new port/auth/credential
- [ ] License gate green (no GPL/Commons-Clause in runtime)
- [ ] Relevant `docs/` updated; no out-of-scope feature added
If any box is unchecked, **do not merge** — fix or stop and ask.

## Which review to run when
- Any change to `risk/`, `execution/`, `autonomy/`, `kill_switch`, or the lockout → **safety review** (`docs/archive/19` §19.1), evidence required (a passing test, not "I couldn't find a problem").
- Any UI/3D change → confirm **no CLI/stdout**, honesty overlays present, read-only + control-commands only.
- Any model/gate change → **validation review** (`docs/04`): walk-forward, DSR/PBO on honest trial count, benchmarks, kill-criteria.
- Any dependency change → **license review** (`pip-licenses`; permissive only).

## Rules that override convenience
- **M4 (the gate) before M8 (autonomy).** Never run the learning loop without the judge.
- **Tests-first for safety.** A safety/honesty behavior without a test that proves it does not exist.
- **One `Order` constructor.** Never add another path.
- **Ask, don't assume.** Ambiguity, a missing spec, or a conflict with a non-negotiable → stop and ask (see `GUARDRAILS.md` "STOP and ask when…").
- **Smallest safe step.** Prefer the least code that satisfies the milestone; delete anything that doesn't earn its place (ablation applies to code too).

## Session hygiene
Start each session by loading `CLAUDE.md`; state which milestone you're on and its exit gate; end by summarizing what changed, what's green, and what's next. Keep `data/`, `runs/`, `*.duckdb/parquet/jsonl` out of git.
