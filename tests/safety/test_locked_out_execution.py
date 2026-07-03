import pytest

from lqe.execution._locked_out import LiveBrokerAdapter


def test_live_broker_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(NotImplementedError):
        LiveBrokerAdapter()


def test_live_broker_adapter_declares_not_paper() -> None:
    assert LiveBrokerAdapter.is_paper is False
