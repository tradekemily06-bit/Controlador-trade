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


def _setup(tmp_path, exchange=None, refresh=None):
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

