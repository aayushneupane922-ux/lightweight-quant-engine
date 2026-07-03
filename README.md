# lightweight-quant-engine

A **local, paper-only, autonomous quant research simulator**: a large catalog of quant + statistical models running live on real-time crypto data in simulation, driven by an **LLM + ML engine room** in a continuous learn → adjust → learn loop, with an **aggressive autopilot** you can ride and a **3D neural-web** view. Runs on your machine, GUI in a browser on `localhost`, ~$0/month, and it **cannot place a real trade or claim a profit.**

**The honest core:** exploration is free in the sandbox, but the equity curve you *watch* (the tracked book) only accepts changes that pass out-of-sample validation, and it de-risks — never chases — on degradation. The **system** learns on history, runs the validated result live, watches live for decay, and re-learns on history when it decays; the LLM steers and explains, the math decides.

## Status: v2.0 (v1.0's M0–M12 plus v2.0's M13–M17, all complete)

The engine is built — M0–M12 (v1.0) and M13–M17 (v2.0, `docs/12-v2-roadmap.md`: a complete catalog, `lqe live` as a real CLI subcommand with resume, and real CI coverage for the LLM/heavy-model path) done, verified, and tagged. **To run it, read [USER-GUIDE.md](USER-GUIDE.md)**; to understand how every piece works and how to operate/extend it, read **[COMPONENT-GUIDE.md](COMPONENT-GUIDE.md)**; the release safety/honesty review with evidence is in [M12-RELEASE-REVIEW.md](M12-RELEASE-REVIEW.md) (v1.0) and [V2-RELEASE-REVIEW.md](V2-RELEASE-REVIEW.md) (v2.0); the developer orientation is in [HANDOFF.md](HANDOFF.md).

```
pip install -e ".[ui,search,dev]"
lqe doctor          # read-only health check (lockout, config, catalog, license gate)
python run.py       # serve the Obsidian Desk on 127.0.0.1 (paper-only)
```

On Windows, double-click **`run.bat`** instead of `run.py` for a real
zero-terminal launch — it calls this project's `.venv` explicitly, so it
doesn't depend on whatever Python happens to be file-associated on the
machine.

The sections below are the original **planning package** the engine was built from — kept for provenance.

## Operating files (the agent's rails — start here)
| File | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | The constitution — loaded every session (rules, invariants, first action) |
| [GUARDRAILS.md](GUARDRAILS.md) | The boundary fence — NEVER list, out-of-scope list, when to STOP and ask |
| [WORKFLOW.md](WORKFLOW.md) | The per-change loop, definition of done, review gates, commit/tag discipline |
| [GLOSSARY.md](GLOSSARY.md) | Canonical vocabulary — use these exact terms |

## The spec set (`docs/`)
| # | File | For |
|---|---|---|
| 00 | [vision-and-objective](00-vision-and-objective.md) | What it is, the honest objective, non-negotiables |
| 01 | [system-architecture](01-system-architecture.md) | Local engine + localhost GUI + the autonomy engine room |
| 02 | [autonomy-autopilot-and-learning-loop](02-autonomy-autopilot-and-learning-loop.md) | LLM+Optuna+Validator loop, aggressive autopilot |
| 03 | [model-catalog](03-model-catalog.md) | Big catalog via adapters, intake, honesty at scale |
| 04 | [validation-and-overfitting-protocol](04-validation-and-overfitting-protocol.md) | The promotion gate — the real product |
| 05 | [ui-and-3d-visualization](05-ui-and-3d-visualization.md) | Obsidian Desk terminal + the 3D neural-web |
| 06 | [engine-data-risk-and-audit](06-engine-data-risk-and-audit.md) | Deterministic core, data, sim risk, audit/replay |
| 07 | [cost-stack-and-local-llm](07-cost-stack-and-local-llm.md) | ~$0 stack + Ollama local LLM |
| 08 | [build-plan-and-claude-code-prompts](08-build-plan-and-claude-code-prompts.md) | Master prompt + milestone prompts |
| 09 | [decision-log-risks-open-questions](09-decision-log-risks-open-questions.md) | Decisions, corrections, risks, open questions |
| 10 | [production-roadmap](10-production-roadmap.md) | Step-by-step build roadmap: M0–M12, gates, releases |
| 11 | [technical-spec](11-technical-spec.md) | Implementation contracts: interfaces, schemas, flows |
| 12 | [v2-roadmap](12-v2-roadmap.md) | Post-v1.0 roadmap: M13–M17 (catalog complete, `lqe live`, CI for the LLM/heavy-model path) |
| 13 | [v3-roadmap](13-v3-roadmap.md) | Post-v2.0 roadmap: M18–M22 (one-click launch, institutional UI, live blotter, engine-room conversation) |
| 14 | [v4-catalog-expansion](14-v4-catalog-expansion.md) | Post-v3.0 roadmap: M23–M26 (measured catalog diversification by return-driver sleeve, not headcount) |

Mockups (open in a browser): [obsidian-desk-model-floor](mockups/obsidian-desk-model-floor.html) · [neural-engine-3d](mockups/neural-engine-3d.html) · [neural-engine-plasma](mockups/neural-engine-plasma.html) · [neural-engine-holo](mockups/neural-engine-holo.html) · [neural-engine-observatory](mockups/neural-engine-observatory.html)

## What to give Claude Code
Put **`CLAUDE.md` at the repo root** and the **operating files + `docs/00–11`** in the repo. Claude Code auto-loads `CLAUDE.md` every session and reads the specific doc for the current milestone — you don't paste them all into one prompt.
- ✅ Include: `CLAUDE.md`, `GUARDRAILS.md`, `WORKFLOW.md`, `GLOSSARY.md`, `docs/00–11`, the mockups.
- ❌ Exclude from what it builds from: `docs/archive/` (37 superseded files) — kept for human reference only; feeding stale, conflicting design docs causes drift.

## First build action
Read `docs/00,01,02,04,06,10,11` + `GUARDRAILS.md` + `WORKFLOW.md`, then run **Milestone 1** (`docs/10`): deterministic core + paper-only lockout + audit, with tests, and stop for review. **M4 (the validation gate) must exist before M8 (the autonomy loop)** — never run the learner without the judge.

## Archive
`docs/archive/` holds the earlier phased research (37 files) — background only, superseded by this set.
