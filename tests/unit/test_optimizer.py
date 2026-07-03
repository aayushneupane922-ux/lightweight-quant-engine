"""The Optuna optimizer adapter (docs/11 §11.2/§11.6): seeded and
reproducible, records every trial, respects int vs float ranges.
"""

from __future__ import annotations

from lqe.autonomy.optimizer import OptunaOptimizer, ParamRange, SearchSpace


def _space() -> SearchSpace:
    return SearchSpace(
        model_id="demo",
        ranges={
            "x": ParamRange(low=-10, high=10, is_int=True),
            "y": ParamRange(low=-5.0, high=5.0, is_int=False),
        },
    )


def _objective(params: dict[str, float]) -> float:
    # unique maximum at x=3, y=1.5
    return -((params["x"] - 3) ** 2) - (params["y"] - 1.5) ** 2


def test_same_seed_gives_identical_results() -> None:
    opt = OptunaOptimizer()
    a = opt.study(_space(), _objective, n_trials=30, seed=42)
    b = opt.study(_space(), _objective, n_trials=30, seed=42)
    assert a.best_params == b.best_params
    assert a.best_value == b.best_value
    assert [t.params for t in a.trials] == [t.params for t in b.trials]


def test_records_every_trial_in_order() -> None:
    opt = OptunaOptimizer()
    result = opt.study(_space(), _objective, n_trials=15, seed=1)
    assert len(result.trials) == 15
    assert [t.index for t in result.trials] == list(range(15))


def test_int_ranges_yield_integers_and_search_approaches_the_optimum() -> None:
    opt = OptunaOptimizer()
    result = opt.study(_space(), _objective, n_trials=60, seed=7)
    assert isinstance(result.best_params["x"], int)
    # with 60 seeded TPE trials it should land near the true optimum x=3
    assert abs(result.best_params["x"] - 3) <= 2


def test_different_seeds_can_differ() -> None:
    opt = OptunaOptimizer()
    a = opt.study(_space(), _objective, n_trials=20, seed=1)
    b = opt.study(_space(), _objective, n_trials=20, seed=2)
    # not a hard guarantee, but the trial sequences should not be identical
    assert [t.params for t in a.trials] != [t.params for t in b.trials]
