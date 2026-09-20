from execution.ctrader_demo_connection import (
    CTraderCredentials,
    CTraderDemoConnection,
    InMemoryTokenProvider,
)


class FakeClient:
    def __init__(self):
        self.connected = False
        self.disconnected = False

    def connect(self):
        self.connected = True

    def send(self, request):
        return request

    def disconnect(self):
        self.disconnected = True


def test_token_provider_expires_without_persisting_secret():
    provider = InMemoryTokenProvider()
    provider.set_token("runtime-token", 60, "runtime-refresh")
    snapshot = provider.snapshot()
    assert snapshot.has_access_token is True
    assert snapshot.has_refresh_token is True
    assert snapshot.expires_in > 0


def test_connection_is_demo_only_and_requires_token():
    provider = InMemoryTokenProvider()
    clients = []

    def factory(client_id, client_secret):
        client = FakeClient()
        clients.append((client_id, client_secret, client))
        return client

    connection = CTraderDemoConnection(
        CTraderCredentials("client", "secret"),
        provider,
        factory,
    )

    try:
        connection.connect()
        assert False, "deveria exigir token"
    except RuntimeError as exc:
        assert "autorize" in str(exc)
    assert clients == []


def test_connection_uses_demo_endpoint_and_runtime_credentials():
    provider = InMemoryTokenProvider()
    provider.set_token("runtime-token", 60)
    created = []

    def factory(client_id, client_secret):
        client = FakeClient()
        created.append((client_id, client_secret, client))
        return client

    connection = CTraderDemoConnection(
        CTraderCredentials("client", "secret"),
        provider,
        factory,
    )
    client = connection.connect()

    assert connection.endpoint == ("demo.ctraderapi.com", 5035)
    assert client.connected is True
    assert created[0][0:2] == ("client", "secret")

def test_oauth_exchange_keeps_client_secret_out_of_url(monkeypatch):
    from execution import ctrader_demo_runtime

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"accessToken":"token","expiresIn":60}'

    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ctrader_demo_runtime, "urlopen", fake_urlopen)
    provider = ctrader_demo_runtime.exchange_authorization_code(
        CTraderCredentials("client", "secret"),
        "auth-code",
        "https://example.test/callback",
    )

    request = captured["request"]
    assert request.method == "POST"
    assert "secret" not in request.full_url
    assert b"client_secret=secret" in request.data
    assert provider.snapshot().has_access_token is True
