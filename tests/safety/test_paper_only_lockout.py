from decimal import Decimal

import pytest

from lqe.core.config import Config, assert_paper_only
from lqe.core.errors import ConfigError, LockoutViolation

VALID_CONFIG: dict[str, object] = {
    "engine": {
        "mode": "paper",
        "clock": "wallclock",
        "seed": 1,
        "base_currency": "USDT",
        "starting_cash": Decimal("10000"),
    },
    "execution": {"adapter": "paper"},
    "data": {
        "adapter": "ccxt",
        "exchange": "binance",
        "symbols": ["BTC-USDT"],
        "timeframe": "1m",
    },
}


def test_valid_paper_config_loads() -> None:
    config = Config.from_dict(VALID_CONFIG)
    assert config.engine.mode == "paper"
    assert config.execution.adapter == "paper"


def test_backtest_mode_loads() -> None:
    engine_overrides = {**VALID_CONFIG["engine"], "mode": "backtest", "clock": "replay"}  # type: ignore[dict-item]
    data = {**VALID_CONFIG, "engine": engine_overrides}
    config = Config.from_dict(data)
    assert config.engine.mode == "backtest"


def test_config_rejects_live_mode() -> None:
    data = {**VALID_CONFIG, "engine": {**VALID_CONFIG["engine"], "mode": "live"}}  # type: ignore[dict-item]
    with pytest.raises(ConfigError):
        Config.from_dict(data)


def test_config_rejects_non_paper_execution_adapter() -> None:
    data = {**VALID_CONFIG, "execution": {"adapter": "binance_live"}}
    with pytest.raises(ConfigError):
        Config.from_dict(data)


def test_config_is_immutable() -> None:
    config = Config.from_dict(VALID_CONFIG)
    with pytest.raises(Exception):  # noqa: B017 — pydantic frozen-model error type varies
        config.engine.mode = "backtest"


def test_assert_paper_only_passes_for_paper_adapter() -> None:
    assert_paper_only(True)  # must not raise


def test_assert_paper_only_rejects_non_paper_adapter() -> None:
    with pytest.raises(LockoutViolation):
        assert_paper_only(False)
