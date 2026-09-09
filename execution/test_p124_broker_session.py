import pytest

from execution.p124_broker_session import (
    BrokerSessionBoundary,
    BrokerSessionObservation,
    BrokerSessionStatus,
)


def test_only_authenticated_session_is_usable():
    assert BrokerSessionBoundary.is_usable(
        BrokerSessionObservation(BrokerSessionStatus.AUTHENTICATED, "ok")
    ) is True


@pytest.mark.parametrize(
    "status",
    [
        BrokerSessionStatus.EXPIRED,
        BrokerSessionStatus.REVOKED,
        BrokerSessionStatus.UNAVAILABLE,
        BrokerSessionStatus.UNKNOWN,
    ],
)
def test_non_authenticated_session_fails_closed(status):
    assert BrokerSessionBoundary.is_usable(
        BrokerSessionObservation(status, "blocked")
    ) is False


def test_invalid_observation_fails_closed():
    with pytest.raises(ValueError):
        BrokerSessionBoundary.validate(None)
    with pytest.raises(ValueError):
        BrokerSessionBoundary.validate(BrokerSessionObservation(BrokerSessionStatus.AUTHENTICATED, " "))
