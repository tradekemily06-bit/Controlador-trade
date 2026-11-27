from datetime import datetime, timedelta, timezone
from integration.tenant_oauth_state_vault import TenantOAuthStateVault
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry

def _pending(connections, owner, alias="cTrader demo"):
    return connections.record_pending_connection(
        owner, provider_id="ctrader_open_api", account_alias=alias,
        account_reference="oauth-pending-" + alias,
        capabilities=["candles:read", "account-mode:demo"])

def test_oauth_state_is_one_time_and_persists_only_hash(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account = _pending(connections, owner)
    vault = TenantOAuthStateVault(tmp_path / "oauth.sqlite3", connections)
    issued = vault.issue(owner, connection_id=account["connection_id"], provider_id="ctrader_open_api")
    assert issued["state_reveal"] == "ONE_TIME"
    assert len(issued["state"]) >= 40
    assert vault.consume(issued["state"]) == (owner, account["connection_id"], "ctrader_open_api")
    assert vault.consume(issued["state"]) is None
    with vault._connect() as db:
        row = db.execute("SELECT state_hash FROM tenant_oauth_states").fetchone()
    assert row[0] != issued["state"]

def test_oauth_state_cannot_be_issued_for_another_tenant_or_non_pending_connection(tmp_path):
    owner, other = TenantContext("tenant-a", "alice"), TenantContext("tenant-b", "bob")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account = _pending(connections, owner)
    vault = TenantOAuthStateVault(tmp_path / "oauth.sqlite3", connections)
    try:
        vault.issue(other, connection_id=account["connection_id"], provider_id="ctrader_open_api")
    except PermissionError:
        pass
    else:
        raise AssertionError("another tenant must not issue state for this connection")
    connected = connections.record_verified_connection(
        owner, provider_id="ctrader_open_api", account_alias="already connected",
        account_reference="already-connected", capabilities=["candles:read"], adapter_verified=True)
    try:
        vault.issue(owner, connection_id=connected["connection_id"], provider_id="ctrader_open_api")
    except PermissionError:
        pass
    else:
        raise AssertionError("OAuth state must not be issued for a non-pending connection")

def test_oauth_state_expiry_and_provider_allowlist(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account = _pending(connections, owner)
    vault = TenantOAuthStateVault(tmp_path / "oauth.sqlite3", connections)
    issued = vault.issue(owner, connection_id=account["connection_id"], provider_id="ctrader_open_api")
    with vault._connect() as db:
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.execute("UPDATE tenant_oauth_states SET expires_at=?", (expired,))
    assert vault.consume(issued["state"]) is None
    assert vault.consume("short") is None
    try:
        vault.issue(owner, connection_id=account["connection_id"], provider_id="unknown_provider")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown OAuth provider must be rejected")
