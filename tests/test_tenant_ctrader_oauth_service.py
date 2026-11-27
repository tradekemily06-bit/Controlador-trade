import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from integration.tenant_oauth_state_vault import TenantOAuthStateVault
from integration.tenant_oauth_token_vault import TenantOAuthTokenVault
from integration.tenant_ctrader_oauth_service import TenantCTraderOAuthService
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


class TestCipher:
    _mask = b"unit-test-only"

    def _xor(self, data):
        return bytes(value ^ self._mask[i % len(self._mask)] for i, value in enumerate(data))

    def encrypt(self, plaintext, *, associated_data):
        return {"key_id": "test", "ciphertext": hashlib.sha256(associated_data).digest() + self._xor(plaintext)}

    def decrypt(self, ciphertext, *, key_id, associated_data):
        tag = hashlib.sha256(associated_data).digest()
        if key_id != "test" or not ciphertext.startswith(tag):
            raise ValueError("authentication failed")
        return self._xor(ciphertext[len(tag):])


def _setup(tmp_path, exchange=None, refresh=None, on_tokens_stored=None):
    owner = TenantContext("tenant-a", "alice")
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    connections = TenantProviderConnectionRegistry(storage)
    account = connections.record_pending_connection(
        owner, provider_id="ctrader_open_api", account_alias="demo",
        account_reference="pending-demo", capabilities=["candles:read"])
    state = TenantOAuthStateVault(tmp_path / "state.sqlite3", connections)
    tokens = TenantOAuthTokenVault(tmp_path / "tokens.sqlite3", connections, TestCipher())
    service = TenantCTraderOAuthService(
        connections, state, tokens, client_id="client-id",
        redirect_uri="https://app.example.com/oauth/ctrader/callback",
        exchange_code=exchange or (lambda code, redirect: {
            "accessToken": "access-token", "refreshToken": "refresh-token", "expiresIn": 3600
        }),
        refresh_tokens=refresh,
        on_tokens_stored=on_tokens_stored,
    )
    return owner, connections, account, tokens, service


def test_begin_creates_state_bound_authorization_url_without_connecting(tmp_path):
    owner, connections, account, tokens, service = _setup(tmp_path)
    result = service.begin(owner, connection_id=account["connection_id"])
    query = parse_qs(urlparse(result["authorization_url"]).query)
    assert query["client_id"] == ["client-id"]
    assert query["scope"] == ["accounts"]
    assert query["redirect_uri"] == ["https://app.example.com/oauth/ctrader/callback"]
    assert query["state"][0]
    assert result["state_reveal"] == "ONE_TIME"
    assert connections.list_connections(owner)[0]["status"] == "PENDING"


def test_callback_stores_encrypted_tokens_but_does_not_connect_account(tmp_path):
    owner, connections, account, tokens, service = _setup(tmp_path)
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    result = service.complete_callback(state=state, code="one-time-code")
    assert result["status"] == "OAUTH_TOKEN_STORED_PENDING_DEMO_HANDSHAKE"
    assert result["account_connected"] is False
    assert tokens.resolve(owner, account["connection_id"])["access_token"] == "access-token"
    assert connections.list_connections(owner)[0]["status"] == "PENDING"
    with pytest.raises(PermissionError):
        service.complete_callback(state=state, code="one-time-code")


def test_callback_rejects_invalid_expiry_and_does_not_store_tokens(tmp_path):
    owner, connections, account, tokens, service = _setup(
        tmp_path, exchange=lambda code, redirect: {
            "accessToken": "access-token", "expiresIn": 0
        }
    )
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    with pytest.raises(ValueError):
        service.complete_callback(state=state, code="code")
    assert tokens.resolve(owner, account["connection_id"]) is None


def test_begin_rejects_other_tenant_connection(tmp_path):
    owner, connections, account, tokens, service = _setup(tmp_path)
    other = TenantContext("tenant-b", "bob")
    with pytest.raises(PermissionError):
        service.begin(other, connection_id=account["connection_id"])

def test_refresh_rotates_tokens_and_persists_new_encrypted_values(tmp_path):
    owner, connections, account, tokens, service = _setup(
        tmp_path,
        refresh=lambda old: {
            "accessToken": "rotated-access",
            "refreshToken": "rotated-refresh",
            "expiresIn": 7200,
            "tokenType": "bearer",
        },
    )
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    service.complete_callback(state=state, code="code")
    result = service.refresh(owner, connection_id=account["connection_id"])
    assert result["status"] == "TOKEN_REFRESHED_ENCRYPTED"
    resolved = tokens.resolve(owner, account["connection_id"])
    assert resolved["access_token"] == "rotated-access"
    assert resolved["refresh_token"] == "rotated-refresh"
    assert resolved["scopes"] == ["accounts"]
    assert result["secret_material_returned"] is False


def test_refresh_fails_closed_without_refresh_client(tmp_path):
    owner, connections, account, tokens, service = _setup(tmp_path)
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    service.complete_callback(state=state, code="code")
    with pytest.raises(RuntimeError):
        service.refresh(owner, connection_id=account["connection_id"])

def test_service_rejects_trading_scope_for_read_only_application(tmp_path):
    owner, connections, account, tokens, service = _setup(tmp_path)
    with pytest.raises(ValueError):
        TenantCTraderOAuthService(
            connections,
            service.state_vault,
            tokens,
            client_id="client-id",
            redirect_uri="https://app.example.com/ctrader/callback",
            exchange_code=lambda code, redirect: {},
            scope="trading",
        )



def test_provision_creates_unique_pending_accounts_and_starts_oauth(tmp_path):
    owner, connections, _account, _tokens, service = _setup(tmp_path)
    first = service.provision(owner, account_alias="Demo Principal")
    second = service.provision(owner, account_alias="Demo Secundaria")

    assert first["status"] == "PENDING_OAUTH"
    assert first["account_connected"] is False
    assert first["authorization_url"].startswith("https://")
    assert second["connection_id"] != first["connection_id"]
    accounts = connections.list_connections(owner)
    provisioned = [item for item in accounts if item["account_alias"].startswith("Demo ")]
    assert len(provisioned) == 2
    assert all(item["status"] == "PENDING" for item in provisioned)
    assert all(item["account_reference"].startswith("pending:") for item in provisioned)
    assert all("candles:stream" in item["capabilities"] for item in provisioned)


def test_provision_rejects_untrusted_tenant_context(tmp_path):
    _owner, _connections, _account, _tokens, service = _setup(tmp_path)
    with pytest.raises(PermissionError):
        service.provision(None, account_alias="Demo")


def test_refresh_can_rotate_after_access_token_expiry_without_exposing_it_to_adapters(tmp_path):
    from datetime import datetime, timedelta, timezone

    owner, connections, account, tokens, service = _setup(
        tmp_path,
        refresh=lambda old: {
            "accessToken": "renewed-access",
            "refreshToken": "renewed-refresh",
            "expiresIn": 3600,
        },
    )
    tokens.store(
        owner,
        connection_id=account["connection_id"],
        provider_id="ctrader_open_api",
        token_set={
            "access_token": "expired-access",
            "refresh_token": "still-valid-refresh",
        },
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        scopes=("accounts",),
    )

    # Normal provider resolution must never return an expired access token.
    assert tokens.resolve(owner, account["connection_id"]) is None

    # Only the OAuth refresh path may resolve the encrypted refresh material.
    result = service.refresh(owner, connection_id=account["connection_id"])
    assert result["status"] == "TOKEN_REFRESHED_ENCRYPTED"
    resolved = tokens.resolve(owner, account["connection_id"])
    assert resolved["access_token"] == "renewed-access"
    assert resolved["refresh_token"] == "renewed-refresh"


def test_refresh_uses_injected_shared_lease_provider(tmp_path):
    from contextlib import contextmanager

    owner, connections, account, tokens, service = _setup(
        tmp_path,
        refresh=lambda old: {
            "accessToken": "shared-lock-access",
            "refreshToken": "shared-lock-refresh",
            "expiresIn": 3600,
        },
    )
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    service.complete_callback(state=state, code="code")

    class SharedLeaseProvider:
        def __init__(self):
            self.keys = []
        @contextmanager
        def acquire(self, key, *, lease_seconds, wait_seconds):
            self.keys.append((key, lease_seconds, wait_seconds))
            yield

    provider = SharedLeaseProvider()
    service.refresh_lease_provider = provider
    result = service.refresh(owner, connection_id=account["connection_id"])

    assert result["status"] == "TOKEN_REFRESHED_ENCRYPTED"
    assert provider.keys == [(
        f"oauth-refresh:{owner.tenant_id}:{owner.subject_id}:{account['connection_id']}",
        90, 15,
    )]


def test_refresh_fails_closed_when_shared_lease_is_unavailable(tmp_path):
    owner, connections, account, tokens, service = _setup(
        tmp_path,
        refresh=lambda old: pytest.fail("refresh must not run without lease"),
    )
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    service.complete_callback(state=state, code="code")

    class BusyLeaseProvider:
        def acquire(self, key, *, lease_seconds, wait_seconds):
            return None

    service.refresh_lease_provider = BusyLeaseProvider()
    with pytest.raises(TimeoutError):
        service.refresh(owner, connection_id=account["connection_id"])


def test_callback_registers_trusted_owner_for_background_refresh_only_after_token_storage(tmp_path):
    registrations = []
    owner, connections, account, tokens, service = _setup(
        tmp_path, on_tokens_stored=registrations.append
    )
    started = service.begin(owner, connection_id=account["connection_id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]

    assert registrations == []
    result = service.complete_callback(state=state, code="code")

    assert registrations == [owner]
    assert result["account_connected"] is False
    assert tokens.resolve(owner, account["connection_id"])["refresh_token"] == "refresh-token"
