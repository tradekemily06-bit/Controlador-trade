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


def test_oauth_redirect_uri_rejects_http_embedded_credentials_and_fragments():
    invalid = (
        "http://example.test/callback",
        "https://user:pass@example.test/callback",
        "https://example.test/callback#fragment",
    )
    for redirect_uri in invalid:
        try:
            CTraderOAuthConfig(client_id="39411", redirect_uri=redirect_uri)
        except ValueError:
            continue
        raise AssertionError(f"unsafe redirect URI accepted: {redirect_uri}")


def test_oauth_inputs_have_bounded_size():
    from execution.ctrader_demo_runtime import exchange_authorization_code
    from execution.ctrader_demo_connection import CTraderCredentials

    credentials = CTraderCredentials(client_id="id", client_secret="secret")
    with __import__("pytest").raises(ValueError, match="authorization_code"):
        exchange_authorization_code(credentials, "x" * 4097, "https://example.test/callback")
    with __import__("pytest").raises(ValueError, match="redirect_uri"):
        exchange_authorization_code(credentials, "code", "https://example.test/" + "x" * 2048)
