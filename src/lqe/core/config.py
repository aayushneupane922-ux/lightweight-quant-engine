"""Pydantic config with the paper-only lockout (docs/11 §11.5).

`engine`/`execution`/`data` exist now — `strategies`/`risk`/`autopilot`/
`reporting` join the schema as the milestones that use them (M3/M5/M8/M12)
land, so this schema never carries a config knob nothing reads.

`engine.mode` and `execution.adapter` are closed `Literal`s: pydantic
rejects any value outside them at validation time, so `mode: live` (or any
non-`paper` adapter) cannot even be expressed, let alone loaded.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from lqe.core.errors import ConfigError, LockoutViolation
from lqe.core.types import Symbol, Timeframe

_FROZEN = ConfigDict(frozen=True)


class EngineConfig(BaseModel):
    model_config = _FROZEN

    mode: Literal["backtest", "paper"]
    clock: Literal["replay", "wallclock"]
    seed: int
    base_currency: str
    starting_cash: Decimal


class ExecutionConfig(BaseModel):
    model_config = _FROZEN

    adapter: Literal["paper"]


class DataConfig(BaseModel):
    model_config = _FROZEN

    adapter: Literal["ccxt", "csv_replay"]
    exchange: str
    symbols: list[Symbol]
    timeframe: Timeframe
    replay_bundle: str | None = None


class Config(BaseModel):
    model_config = _FROZEN

    engine: EngineConfig
    execution: ExecutionConfig
    data: DataConfig

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Config:
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc


def assert_paper_only(is_paper: bool) -> None:
    """The startup check: the wired execution adapter must be paper-only."""
    if not is_paper:
        raise LockoutViolation("Execution adapter must be paper-only (is_paper=True).")
