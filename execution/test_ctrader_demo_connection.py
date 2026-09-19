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


def test_account_identity_is_bound_only_after_broker_confirmation():
    provider = InMemoryTokenProvider()
    provider.set_token("runtime-token", 60)
    connection = CTraderDemoConnection(
        CTraderCredentials("client", "secret"), provider, lambda _id, _secret: FakeClient()
    )

    request = connection.account_auth_request(123)
    assert request.ctidTraderAccountId == 123
    assert connection.account_id is None
    assert provider.snapshot().account_id is None

    connection.confirm_account_authenticated(123)
    assert connection.account_id == 123
    assert provider.snapshot().account_id == "123"


def test_account_confirmation_cannot_bind_unrequested_account():
    provider = InMemoryTokenProvider()
    provider.set_token("runtime-token", 60)
    connection = CTraderDemoConnection(
        CTraderCredentials("client", "secret"), provider, lambda _id, _secret: FakeClient()
    )
    connection.account_auth_request(123)

    try:
        connection.confirm_account_authenticated(456)
        assert False, "conta não solicitada não deveria ser vinculada"
    except ValueError as exc:
        assert "não corresponde" in str(exc)
    assert connection.account_id is None
    assert provider.snapshot().account_id is None
