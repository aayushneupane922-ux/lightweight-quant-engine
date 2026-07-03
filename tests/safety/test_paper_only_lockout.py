import json
from decimal import Decimal
from pathlib import Path

import pytest

from lqe.core.config import Config, assert_paper_only, load_config
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
    # live/real/prod modes are refused by name as an explicit LockoutViolation
    for locked in ("live", "real", "prod", "production"):
        data = {**VALID_CONFIG, "engine": {**VALID_CONFIG["engine"], "mode": locked}}  # type: ignore[dict-item]
        with pytest.raises(LockoutViolation):
            Config.from_dict(data)


def test_config_rejects_non_paper_execution_adapter() -> None:
    data = {**VALID_CONFIG, "execution": {"adapter": "binance_live"}}
    with pytest.raises(LockoutViolation):
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


# --- load_config: the lockout is exercised by a real file-load path -------

_JSON_CONFIG: dict[str, object] = {
    "engine": {
        "mode": "paper", "clock": "wallclock", "seed": 1,
        "base_currency": "USDT", "starting_cash": 10000,
    },
    "execution": {"adapter": "paper"},
    "data": {"adapter": "ccxt", "exchange": "binance", "symbols": ["BTC-USDT"], "timeframe": "1m"},
}


def test_load_config_reads_a_valid_json_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_JSON_CONFIG), encoding="utf-8")
    config = load_config(path)
    assert config.engine.mode == "paper"
    assert config.execution.adapter == "paper"


def test_load_config_reads_a_valid_toml_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[engine]\nmode='paper'\nclock='replay'\nseed=1\nbase_currency='USDT'\nstarting_cash=10000\n"
        "[execution]\nadapter='paper'\n"
        "[data]\nadapter='csv_replay'\nexchange='binance'\nsymbols=['BTC-USDT']\ntimeframe='1m'\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.engine.clock == "replay"


def test_load_config_rejects_live_mode_from_a_file(tmp_path: Path) -> None:
    live: dict[str, object] = {
        **_JSON_CONFIG,
        "engine": {
            "mode": "live", "clock": "wallclock", "seed": 1,
            "base_currency": "USDT", "starting_cash": 10000,
        },
    }
    path = tmp_path / "live.json"
    path.write_text(json.dumps(live), encoding="utf-8")
    with pytest.raises(LockoutViolation):
        load_config(path)


def test_load_config_rejects_malformed_config(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"engine": {"mode": "paper"}}), encoding="utf-8")  # missing sections
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_config_rejects_unknown_extension(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("engine: {}", encoding="utf-8")
    with pytest.raises(ConfigError, match="unsupported config format"):
        load_config(path)


def test_load_config_missing_file_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config("does-not-exist.json")
