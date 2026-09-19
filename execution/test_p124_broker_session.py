import pytest

from execution.p124_broker_session import (
    BrokerSessionBoundary,
    BrokerSessionObservation,
    BrokerSessionStatus,
)


def test_only_authenticated_session_is_usable():
    assert BrokerSessionBoundary.is_usable(
        BrokerSessionObservation(BrokerSessionStatus.AUTHENTICATED, "ok", "acct-1", "sess-1")
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


def test_authenticated_session_requires_account_and_session_identity():
    with pytest.raises(ValueError, match="account_id e session_id"):
        BrokerSessionBoundary.validate(
            BrokerSessionObservation(BrokerSessionStatus.AUTHENTICATED, "ok")
        )


def test_authenticated_session_rejects_partial_identity():
    with pytest.raises(ValueError, match="account_id e session_id"):
        BrokerSessionBoundary.validate(
            BrokerSessionObservation(
                BrokerSessionStatus.AUTHENTICATED,
                "ok",
                account_id="acct-1",
                session_id=None,
            )
        )
