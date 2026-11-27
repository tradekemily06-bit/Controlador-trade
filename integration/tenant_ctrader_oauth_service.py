"""Tenant-scoped cTrader OAuth orchestration.

This service links the one-time OAuth state vault to the encrypted token vault.
It deliberately does not mark an account CONNECTED: a separate DEMO account
selection and authenticated market-data handshake are still required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from execution.p128_ctrader_demo_auth import CTRADER_AUTHORIZATION_URL
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_PROVIDER_ID = "ctrader_open_api"


class TenantCTraderOAuthService:
    """Create tenant-bound consent URLs and persist callback tokens safely."""

    def __init__(
        self,
        connections: Any,
        state_vault: Any,
        token_vault: Any,
        *,
        client_id: str,
        redirect_uri: str,
        exchange_code: Callable[[str, str], Mapping[str, Any]],
        scope: str = "trading",
    ) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant connection registry is required")
        if state_vault is None or not callable(getattr(state_vault, "issue", None)):
            raise ValueError("tenant OAuth state vault is required")
        if token_vault is None or not callable(getattr(token_vault, "store", None)):
            raise ValueError("encrypted tenant OAuth token vault is required")
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("cTrader client_id is required")
        if not isinstance(redirect_uri, str) or not redirect_uri.startswith("https://"):
            raise ValueError("cTrader OAuth redirect_uri must use HTTPS")
        if not callable(exchange_code):
            raise ValueError("OAuth authorization-code exchange is not configured")
        if scope not in {"accounts", "trading"}:
            raise ValueError("unsupported cTrader OAuth scope")
        self.connections = connections
        self.state_vault = state_vault
        self.token_vault = token_vault
        self.client_id = client_id.strip()
        self.redirect_uri = redirect_uri
        self.exchange_code = exchange_code
        self.scope = scope

    def begin(self, context: TenantContext, *, connection_id: str) -> dict[str, Any]:
        owner = require_tenant_context(context)
        account = next(
            (item for item in self.connections.list_connections(owner)
             if item.get("connection_id") == connection_id),
            None,
        )
        if account is None:
            raise PermissionError("cTrader connection does not belong to this identity")
        if account.get("provider_id") != _PROVIDER_ID or account.get("status") != "PENDING":
            raise PermissionError("OAuth is allowed only for an owned pending cTrader connection")
        issued = self.state_vault.issue(
            owner, connection_id=connection_id, provider_id=_PROVIDER_ID
        )
        query = urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "product": "web",
            "state": issued["state"],
        })
        return {
            "connection_id": connection_id,
            "provider_id": _PROVIDER_ID,
            "authorization_url": f"{CTRADER_AUTHORIZATION_URL}?{query}",
            "state_expires_at": issued["expires_at"],
            "state_reveal": "ONE_TIME",
            "execution_authorized": False,
        }

    def complete_callback(self, *, state: str, code: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip() or len(code) > 4096:
            raise ValueError("cTrader authorization code is invalid")
        resolved = self.state_vault.consume(state)
        if not isinstance(resolved, tuple) or len(resolved) != 3:
            raise PermissionError("OAuth state is invalid, expired, or already consumed")
        owner, connection_id, provider_id = resolved
        if provider_id != _PROVIDER_ID:
            raise PermissionError("OAuth state provider mismatch")
        account = next(
            (item for item in self.connections.list_connections(owner)
             if item.get("connection_id") == connection_id),
            None,
        )
        if account is None or account.get("provider_id") != _PROVIDER_ID:
            raise PermissionError("OAuth connection ownership could not be verified")
        if account.get("status") != "PENDING":
            raise PermissionError("cTrader connection is no longer pending")

        # The injected exchange client must keep client_secret server-side and
        # must never log the code or returned token values.
        payload = self.exchange_code(code.strip(), self.redirect_uri)
        if not isinstance(payload, Mapping):
            raise RuntimeError("cTrader OAuth token endpoint returned an invalid response")
        if payload.get("errorCode") or payload.get("error"):
            raise PermissionError("cTrader OAuth authorization was rejected")
        access_token = payload.get("accessToken") or payload.get("access_token")
        refresh_token = payload.get("refreshToken") or payload.get("refresh_token")
        expires_in = payload.get("expiresIn") or payload.get("expires_in")
        if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or not 1 <= expires_in <= 31536000:
            raise ValueError("cTrader OAuth token expiry is invalid")
        token_set = {"access_token": access_token}
        if refresh_token is not None:
            token_set["refresh_token"] = refresh_token
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        ).isoformat()
        stored = self.token_vault.store(
            owner,
            connection_id=connection_id,
            provider_id=_PROVIDER_ID,
            token_set=token_set,
            expires_at=expires_at,
            scopes=(self.scope,),
        )
        return {
            "connection_id": connection_id,
            "provider_id": _PROVIDER_ID,
            "status": "OAUTH_TOKEN_STORED_PENDING_DEMO_HANDSHAKE",
            "token_status": stored.get("status"),
            "expires_at": stored.get("expires_at"),
            "account_connected": False,
            "execution_authorized": False,
        }
