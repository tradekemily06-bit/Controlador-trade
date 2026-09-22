from execution.p124_broker_session import BrokerSessionStatus
from execution.p128_ctrader_demo_auth import (
    CTraderDemoSession,
    CTraderOAuthConfig,
    CTraderOAuthScope,
    CTraderTokenSnapshot,
    new_oauth_state,
    validate_oauth_state,
)


class FakeTokenProvider:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot


def test_authorization_url_is_demo_safe_and_requests_trading_scope():
    config = CTraderOAuthConfig(
        client_id="39411",
        redirect_uri="https://example.test/callback",
        scope=CTraderOAuthScope.TRADING,
    )

    state = new_oauth_state()
    url = config.authorization_url(state=state)

    assert "client_id=39411" in url
    assert "scope=trading" in url
    assert "product=web" in url
    assert "client_secret" not in url


def test_session_is_authenticated_only_with_live_access_token_metadata():
    session = CTraderDemoSession(
        FakeTokenProvider(CTraderTokenSnapshot(3600, True, True))
    )

    observation = session.check_session()

    assert observation.status is BrokerSessionStatus.AUTHENTICATED


def test_session_rejects_missing_token():
    session = CTraderDemoSession(
        FakeTokenProvider(CTraderTokenSnapshot(3600, False, False))
    )

    observation = session.check_session()

    assert observation.status is BrokerSessionStatus.UNAVAILABLE


def test_session_rejects_expired_token():
    session = CTraderDemoSession(
        FakeTokenProvider(CTraderTokenSnapshot(0, True, True))
    )

    observation = session.check_session()

    assert observation.status is BrokerSessionStatus.EXPIRED


def test_oauth_state_is_unpredictable_and_must_match():
    first = new_oauth_state()
    second = new_oauth_state()
    assert len(first) >= 32
    assert first != second
    validate_oauth_state(first, first)

    import pytest
    with pytest.raises(ValueError, match="state OAuth inválido"):
        validate_oauth_state(first, second)


def test_authorization_url_requires_state():
    config = CTraderOAuthConfig(client_id="39411", redirect_uri="https://example.test/callback")
    import pytest
    with pytest.raises(ValueError, match="state OAuth obrigatório"):
        config.authorization_url(state="short")
