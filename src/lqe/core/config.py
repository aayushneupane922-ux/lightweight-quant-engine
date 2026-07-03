"""Pydantic config with the paper-only lockout (docs/11 §11.5).

`engine`/`execution`/`data` exist now — `strategies`/`risk`/`autopilot`/
`reporting` join the schema as the milestones that use them (M3/M5/M8/M12)
land, so this schema never carries a config knob nothing reads.

`engine.mode` and `execution.adapter` are closed `Literal`s: pydantic
rejects any value outside them at validation time, so `mode: live` (or any
non-`paper` adapter) cannot even be expressed, let alone loaded.
"""

from __future__ import annotations

import json
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from lqe.core.errors import ConfigError, LockoutViolation
from lqe.core.types import Symbol, Timeframe

_FROZEN = ConfigDict(frozen=True)

# Any hint of a real-execution mode is refused *by name* before schema
# validation, so a misconfig fails as an explicit LockoutViolation rather
# than a generic "not a valid Literal" — the lockout is a first-class error.
_LOCKED_MODES = frozenset({"live", "real", "prod", "production"})


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
        _reject_live(data)
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc


def _reject_live(data: dict[str, object]) -> None:
    engine = data.get("engine")
    execution = data.get("execution")
    mode = str(engine.get("mode", "")).lower() if isinstance(engine, dict) else ""
    adapter = str(execution.get("adapter", "")).lower() if isinstance(execution, dict) else ""
    if mode in _LOCKED_MODES:
        raise LockoutViolation(
            f"engine.mode={mode!r} is forbidden — this build is paper-only "
            "(LIVE_TRADING_ENABLED=False)."
        )
    if adapter and adapter != "paper":
        raise LockoutViolation(
            f"execution.adapter={adapter!r} is forbidden — only the paper broker is allowed."
        )


def load_config(path: str | Path) -> Config:
    """Load + validate a config file (docs/11 §11.5). JSON or TOML (both
    stdlib — no YAML dependency). Fails closed: a `mode: live` / non-paper
    adapter raises `LockoutViolation`; any other invalid config raises
    `ConfigError`. This is the load-time enforcement of non-negotiable #1."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    text = p.read_text(encoding="utf-8")
    data: object
    if p.suffix == ".toml":
        data = tomllib.loads(text)
    elif p.suffix == ".json":
        data = json.loads(text)
    else:
        raise ConfigError(f"unsupported config format {p.suffix!r}; use .json or .toml")
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping/object")
    return Config.from_dict(data)


def assert_paper_only(is_paper: bool) -> None:
    """The startup check: the wired execution adapter must be paper-only."""
    if not is_paper:
        raise LockoutViolation("Execution adapter must be paper-only (is_paper=True).")
