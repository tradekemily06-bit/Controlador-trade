import base64
from datetime import datetime, timedelta, timezone

from integration.tenant_oauth_token_vault import TenantOAuthTokenVault
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry

class TestOnlyCipher:
    """Reversible fixture only; never use this as a production encryption provider."""
    def encrypt(self, plaintext, *, associated_data):
        return {"key_id": "test-key", "ciphertext": associated_data + b"|" + plaintext}
    def decrypt(self, ciphertext, *, key_id, associated_data):
        if key_id != "test-key" or not ciphertext.startswith(associated_data + b"|"):
            raise ValueError("authentication failed")
        return ciphertext[len(associated_data) + 1:]

def _account(connections, owner, alias="cTrader account"):
    return connections.record_pending_connection(
        owner, provider_id="ctrader_open_api", account_alias=alias,
        account_reference="pending-" + alias, capabilities=["candles:read"])

def test_token_vault_encrypts_and_resolves_only_for_owner(tmp_path):
    owner, other = TenantContext("tenant-a", "alice"), TenantContext("tenant-b", "bob")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account = _account(connections, owner)
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    result = vault.store(
        owner, connection_id=account["connection_id"], provider_id="ctrader_open_api",
        token_set={"access_token": "access-secret", "refresh_token": "refresh-secret"},
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        scopes=("accounts", "trading"),
    )
    assert result["secret_material_returned"] is False
    assert vault.resolve(owner, account["connection_id"])["refresh_token"] == "refresh-secret"
    try:
        vault.resolve(other, account["connection_id"])
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-tenant token resolution must be denied")
    with vault._connect() as db:
        row = db.execute("SELECT ciphertext_b64 FROM tenant_oauth_tokens").fetchone()
    assert b"access-secret" not in base64.b64decode(row[0])

def test_token_vault_binds_ciphertext_to_connection_and_supports_revocation(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    first = _account(connections, owner, "first")
    second = _account(connections, owner, "second")
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    vault.store(owner, connection_id=first["connection_id"], provider_id="ctrader_open_api",
                token_set={"access_token": "secret-one"})
    assert vault.resolve(owner, second["connection_id"]) is None
    assert vault.revoke(owner, first["connection_id"]) is True
    assert vault.resolve(owner, first["connection_id"]) is None
    assert vault.revoke(owner, first["connection_id"]) is False

def test_token_vault_rejects_expired_tokens_and_wrong_provider(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account = _account(connections, owner)
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    vault.store(owner, connection_id=account["connection_id"], provider_id="ctrader_open_api",
                token_set={"access_token": "expired-secret"}, expires_at=past)
    assert vault.resolve(owner, account["connection_id"]) is None
    try:
        vault.store(owner, connection_id=account["connection_id"], provider_id="other",
                    token_set={"access_token": "wrong-provider"})
    except PermissionError:
        pass
    else:
        raise AssertionError("token provider mismatch must be rejected")
