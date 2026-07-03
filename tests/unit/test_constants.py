from lqe import constants


def test_live_trading_is_disabled() -> None:
    assert constants.LIVE_TRADING_ENABLED is False
