from execution.p124_broker_session import BrokerSessionStatus
from execution.p128_ctrader_demo_auth import (
    CTraderDemoSession,
    CTraderOAuthConfig,
    CTraderOAuthScope,
    CTraderTokenSnapshot,
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

    url = config.authorization_url()

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
