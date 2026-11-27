from __future__ import annotations

from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry
from integration.tenant_market_data_sessions import TenantMarketDataSessionRegistry
from integration.tenant_ctrader_account_service import TenantCTraderAccountService


class TokenVault:
    def resolve(self, context, connection_id):
        if context.tenant_id != "tenant-a":
            return None
        return {"access_token": "opaque-access-token"}


class FakeTransport:
    def __init__(self, selected_account=111, *, is_live=False):
        self.selected_account = selected_account
        self.is_live = is_live
        self.calls = []
        self.connected = False

    def connect(self):
        self.connected = True
        self.calls.append("connect")

    def application_auth(self):
        self.calls.append("application_auth")

    def list_accounts(self):
        return (
            {"account_id": 111, "is_live": False},
            {"account_id": 222, "is_live": True},
        )

    def account_details(self, account_id):
        return {"account_id": account_id, "is_live": self.is_live}

    def account_auth(self, account_id):
        self.calls.append(("account_auth", account_id))

    def disconnect(self):
        self.connected = False
        self.calls.append("disconnect")


def setup(tmp_path, *, selected_account=111, is_live=False):
    owner = TenantContext("tenant-a", "alice")
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    connections = TenantProviderConnectionRegistry(storage)
    pending = connections.record_pending_connection(
        owner,
        provider_id="ctrader_open_api",
        account_alias="cTrader DEMO",
        account_reference="pending:opaque-ref",
        capabilities=["candles:read"],
    )
    sessions = TenantMarketDataSessionRegistry(connections)
    transports = []

    def factory(access_token):
        assert access_token == "opaque-access-token"
        transport = FakeTransport(selected_account, is_live=is_live)
        transports.append(transport)
        return transport

    service = TenantCTraderAccountService(
        connections, sessions, TokenVault(), transport_factory=factory
    )
    return owner, connections, sessions, pending, transports, service


def test_list_demo_accounts_hides_real_accounts_and_closes_temporary_transport(tmp_path):
    owner, _connections, _sessions, pending, transports, service = setup(tmp_path)
    result = service.list_demo_accounts(owner, connection_id=pending["connection_id"])
    assert result["accounts"] == [{"account_id": 111, "account_mode": "DEMO"}]
    assert result["real_accounts_exposed"] is False
    assert result["execution_authorized"] is False
    assert transports[0].calls == ["connect", "application_auth", "disconnect"]


def test_selected_demo_account_is_verified_and_bound_to_its_tenant_session(tmp_path):
    owner, connections, sessions, pending, transports, service = setup(tmp_path)
    result = service.connect_demo(
        owner, connection_id=pending["connection_id"], account_id=111
    )
    account = connections.list_connections(owner)[0]
    session = sessions.get(owner, connection_id=pending["connection_id"])
    assert result["status"] == "CONNECTED"
    assert result["account_mode"] == "DEMO"
    assert result["execution_authorized"] is False
    assert account["status"] == "CONNECTED"
    assert account["account_reference"] == "111"
    assert session is not None
    assert session.source == "ctrader:111"
    assert session.adapter.status()["account_mode"] == "DEMO"
    assert "candles:stream" in result["capabilities"]
    assert transports[0].calls[:3] == ["connect", "application_auth", ("account_auth", 111)]


def test_real_account_selection_is_rejected_and_pending_connection_is_preserved(tmp_path):
    owner, connections, sessions, pending, transports, service = setup(
        tmp_path, selected_account=222, is_live=True
    )
    try:
        service.connect_demo(owner, connection_id=pending["connection_id"], account_id=222)
        assert False, "REAL account must be rejected"
    except PermissionError:
        pass
    assert connections.list_connections(owner)[0]["status"] == "PENDING"
    assert sessions.get(owner, connection_id=pending["connection_id"]) is None
    assert transports[0].connected is False


def test_other_tenant_cannot_list_or_bind_oauth_owned_cTrader_account(tmp_path):
    owner, _connections, _sessions, pending, _transports, service = setup(tmp_path)
    other = TenantContext("tenant-b", "bob")
    try:
        service.list_demo_accounts(other, connection_id=pending["connection_id"])
        assert False, "cross-tenant access must be rejected"
    except PermissionError:
        pass
