"""The `Optimizer` (docs/11 §11.2/§11.6, docs/02 §2.1): a thin, seeded
Optuna adapter. Optuna does the numerical search; nothing here judges a
candidate — that's the `Validator`/`PromotionGate`'s job. The LLM (M9)
proposes the space; this runs it.

Determinism (a hard rail, docs/11 §11.8): a `TPESampler(seed=...)` makes
the search reproducible — the same space + seed + objective yields the same
trials and the same best. `optuna` is imported lazily (it lives in the
`search` extra) so the base install and the non-autonomy CLI commands never
need it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True)

# The objective maps a concrete parameter set to a scalar to *maximize*
# (an out-of-sample metric). It must be deterministic given its params.
Objective = Callable[[dict[str, Any]], float]


class ParamRange(BaseModel):
    model_config = _FROZEN
    low: float
    high: float
    is_int: bool = True


class SearchSpace(BaseModel):
    model_config = _FROZEN
    model_id: str
    ranges: dict[str, ParamRange]


class TrialRecord(BaseModel):
    model_config = _FROZEN
    index: int
    params: dict[str, Any]
    value: float


class StudyResult(BaseModel):
    model_config = _FROZEN
    model_id: str
    seed: int
    best_params: dict[str, Any]
    best_value: float
    trials: list[TrialRecord]


def _import_optuna() -> Any:
    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "the autonomy optimizer requires the optional 'search' extra: pip install '.[search]'"
        ) from exc
    return optuna


def safe_search_space(default: SearchSpace, proposed_ranges: dict[str, list[float]]) -> SearchSpace:
    """Merge an LLM-proposed range dict into a model's default space, safely
    (docs/02 §2.5). A proposal may only *narrow* the vetted defaults: each
    proposed `[lo, hi]` is clamped to lie inside the manifest's default
    bounds, and anything malformed or inverted is ignored in favour of the
    default. So the LLM can refine the search but can never escape the
    sane, pre-vetted parameter ranges — its influence is bounded by
    construction, not by a runtime hope.
    """
    merged: dict[str, ParamRange] = {}
    for name, rng in default.ranges.items():
        proposal = proposed_ranges.get(name)
        merged[name] = _clamp_range(rng, proposal)
    return SearchSpace(model_id=default.model_id, ranges=merged)


def _clamp_range(default: ParamRange, proposal: list[float] | None) -> ParamRange:
    if not isinstance(proposal, list) or len(proposal) != 2:
        return default
    lo, hi = min(proposal), max(proposal)
    lo = max(default.low, lo)
    hi = min(default.high, hi)
    if not lo < hi:
        return default  # degenerate after clamping -> keep the vetted default
    return ParamRange(low=lo, high=hi, is_int=default.is_int)


class OptunaOptimizer:
    def study(
        self, space: SearchSpace, objective: Objective, *, n_trials: int, seed: int
    ) -> StudyResult:
        optuna = _import_optuna()
        optuna.logging.set_verbosity(optuna.logging.WARNING)  # no stdout spam into a GUI/log

        trials: list[TrialRecord] = []

        def _optuna_objective(trial: Any) -> float:
            params: dict[str, Any] = {}
            for name, rng in space.ranges.items():
                if rng.is_int:
                    params[name] = trial.suggest_int(name, int(rng.low), int(rng.high))
                else:
                    params[name] = trial.suggest_float(name, rng.low, rng.high)
            value = objective(params)
            trials.append(TrialRecord(index=trial.number, params=params, value=value))
            return value

        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed)
        )
        study.optimize(_optuna_objective, n_trials=n_trials)

        return StudyResult(
            model_id=space.model_id,
            seed=seed,
            best_params=dict(study.best_params),
            best_value=float(study.best_value),
            trials=sorted(trials, key=lambda t: t.index),
        )
