import base64
import hashlib
from datetime import datetime, timedelta, timezone

from integration.tenant_oauth_token_vault import TenantOAuthTokenVault
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


class TestOnlyCipher:
    """Reversible test fixture; not cryptography and never valid in production."""

    _mask = b"unit-test-only-mask"

    @classmethod
    def _xor(cls, value):
        return bytes(byte ^ cls._mask[index % len(cls._mask)]
                     for index, byte in enumerate(value))

    def encrypt(self, plaintext, *, associated_data):
        aad_tag = hashlib.sha256(associated_data).digest()
        return {"key_id": "test-key", "ciphertext": aad_tag + self._xor(plaintext)}

    def decrypt(self, ciphertext, *, key_id, associated_data):
        aad_tag = hashlib.sha256(associated_data).digest()
        if key_id != "test-key" or not ciphertext.startswith(aad_tag):
            raise ValueError("authentication failed")
        return self._xor(ciphertext[len(aad_tag):])


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
    stored_ciphertext = base64.b64decode(row[0])
    assert b"access-secret" not in stored_ciphertext
    assert b"refresh-secret" not in stored_ciphertext


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


def test_token_vault_can_revoke_after_owned_connection_is_disconnected(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account = _account(connections, owner, "disconnected")
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    vault.store(owner, connection_id=account["connection_id"], provider_id="ctrader_open_api",
                token_set={"access_token": "revocation-secret"})
    assert connections.mark_disconnected(owner, connection_id=account["connection_id"]) is True
    assert vault.revoke(owner, account["connection_id"]) is True
    assert vault.resolve(owner, account["connection_id"]) is None


def test_refresh_candidates_lists_only_owned_active_connections_near_expiry(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    other = TenantContext("tenant-b", "bob")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    due = _account(connections, owner, "due")
    future = _account(connections, owner, "future")
    foreign = _account(connections, other, "foreign")
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    vault.store(
        owner, connection_id=due["connection_id"], provider_id="ctrader_open_api",
        token_set={"access_token": "due-access", "refresh_token": "due-refresh"},
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )
    vault.store(
        owner, connection_id=future["connection_id"], provider_id="ctrader_open_api",
        token_set={"access_token": "future-access", "refresh_token": "future-refresh"},
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    )
    vault.store(
        other, connection_id=foreign["connection_id"], provider_id="ctrader_open_api",
        token_set={"access_token": "foreign-access", "refresh_token": "foreign-refresh"},
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
    )

    result = vault.refresh_candidates(owner, within_seconds=900)
    assert [item["connection_id"] for item in result] == [due["connection_id"]]
    assert "access_token" not in result[0]
    assert "refresh_token" not in result[0]


def test_list_refresh_owners_rehydrates_only_non_revoked_owned_ctrader_identities(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    other = TenantContext("tenant-b", "bob")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    account_a = _account(connections, owner, "owner-a")
    account_b = _account(connections, other, "owner-b")
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    vault.store(owner, connection_id=account_a["connection_id"], provider_id="ctrader_open_api",
                token_set={"access_token": "a-access", "refresh_token": "a-refresh"})
    vault.store(other, connection_id=account_b["connection_id"], provider_id="ctrader_open_api",
                token_set={"access_token": "b-access", "refresh_token": "b-refresh"})

    assert vault.list_refresh_owners() == [owner, other]
    assert vault.revoke(owner, account_a["connection_id"]) is True
    assert vault.list_refresh_owners() == [other]


def test_list_refresh_owners_rejects_partial_startup_when_capacity_is_exceeded(tmp_path):
    import pytest

    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    vault = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestOnlyCipher())
    for index in range(2):
        owner = TenantContext(f"tenant-{index}", f"user-{index}")
        account = _account(connections, owner, f"account-{index}")
        vault.store(owner, connection_id=account["connection_id"], provider_id="ctrader_open_api",
                    token_set={"access_token": f"access-{index}", "refresh_token": f"refresh-{index}"})
    with pytest.raises(RuntimeError, match="capacity exceeded"):
        vault.list_refresh_owners(limit=1)
