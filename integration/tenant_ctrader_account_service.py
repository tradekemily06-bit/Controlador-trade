"""Tenant-scoped cTrader OAuth account selection and DEMO adapter binding."""

from __future__ import annotations

from typing import Any, Callable

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context
from security.tenant_provider_connections import TenantProviderConnectionRegistry
from integration.tenant_market_data_sessions import TenantMarketDataSessionRegistry
from integration.ctrader_readonly_market_data_adapter import CTraderReadOnlyMarketDataAdapter


_PROVIDER_ID = "ctrader_open_api"


class TenantCTraderAccountService:
    """List OAuth-owned accounts and bind only an explicitly selected DEMO account."""

    def __init__(
        self,
        connections: TenantProviderConnectionRegistry,
        sessions: TenantMarketDataSessionRegistry,
        token_vault: Any,
        *,
        transport_factory: Callable[[str], Any],
    ) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant connection registry is required")
        if sessions is None or not callable(getattr(sessions, "bind", None)):
            raise ValueError("tenant market-data session registry is required")
        if token_vault is None or not callable(getattr(token_vault, "resolve", None)):
            raise ValueError("encrypted cTrader token vault is required")
        if not callable(transport_factory):
            raise ValueError("trusted cTrader transport factory is required")
        self.connections = connections
        self.sessions = sessions
        self.token_vault = token_vault
        self.transport_factory = transport_factory

    def _owned_pending(self, owner: TenantContext, connection_id: str) -> dict[str, Any]:
        account = next(
            (item for item in self.connections.list_connections(owner)
             if item.get("connection_id") == connection_id),
            None,
        )
        if account is None or account.get("provider_id") != _PROVIDER_ID:
            raise PermissionError("conexão cTrader não pertence a esta identidade")
        if account.get("status") != "PENDING":
            raise PermissionError("seleção de conta cTrader exige conexão pendente")
        return account

    def _access_token(self, owner: TenantContext, connection_id: str) -> str:
        tokens = self.token_vault.resolve(owner, connection_id)
        if not isinstance(tokens, dict) or not isinstance(tokens.get("access_token"), str) or not tokens["access_token"]:
            raise PermissionError("token OAuth cTrader ausente, expirado ou não autorizado")
        return tokens["access_token"]

    def list_demo_accounts(
        self, context: TenantContext, *, connection_id: str
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        self._owned_pending(owner, connection_id)
        access_token = self._access_token(owner, connection_id)
        transport = None
        try:
            transport = self.transport_factory(access_token)
            if transport is None:
                raise RuntimeError("factory cTrader não retornou transporte")
            connect = getattr(transport, "connect", None)
            app_auth = getattr(transport, "application_auth", None)
            list_accounts = getattr(transport, "list_accounts", None)
            if not all(callable(item) for item in (connect, app_auth, list_accounts)):
                raise RuntimeError("transporte cTrader sem operações de listagem seguras")
            connect()
            app_auth()
            raw_accounts = list_accounts()
            demo_accounts = []
            for item in raw_accounts:
                if not isinstance(item, dict):
                    raise ValueError("resposta de contas cTrader inválida")
                account_id = item.get("account_id")
                is_live = item.get("is_live")
                if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
                    raise ValueError("identificador de conta cTrader inválido")
                if not isinstance(is_live, bool):
                    raise PermissionError("Spotware não confirmou o modo da conta")
                if is_live is False:
                    demo_accounts.append({"account_id": account_id, "account_mode": "DEMO"})
            return {
                "connection_id": connection_id,
                "provider_id": _PROVIDER_ID,
                "accounts": demo_accounts,
                "real_accounts_exposed": False,
                "execution_authorized": False,
            }
        finally:
            close = getattr(transport, "disconnect", None) if transport is not None else None
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def connect_demo(
        self, context: TenantContext, *, connection_id: str, account_id: int
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        self._owned_pending(owner, connection_id)
        if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
            raise ValueError("account_id cTrader inválido")
        access_token = self._access_token(owner, connection_id)
        transport = self.transport_factory(access_token)
        adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=account_id)
        try:
            adapter.connect()
            handshake = adapter.handshake()
            if handshake.get("verified") is not True or handshake.get("provider_id") != _PROVIDER_ID:
                raise PermissionError("handshake cTrader não verificado")
            updated = self.connections.mark_connected_after_provider_handshake(
                owner,
                connection_id=connection_id,
                account_reference=handshake["account_reference"],
                capabilities=list(handshake["capabilities"]),
            )
            if updated is not True:
                raise RuntimeError("não foi possível confirmar a conexão cTrader")
            session = self.sessions.bind(
                owner,
                connection_id=connection_id,
                adapter=adapter,
                source=f"ctrader:{account_id}",
                handshake_verified=True,
            )
            return {
                "connection_id": connection_id,
                "provider_id": _PROVIDER_ID,
                "account_reference": handshake["account_reference"],
                "status": "CONNECTED",
                "adapter_status": session["status"],
                "capabilities": list(handshake["capabilities"]),
                "account_mode": "DEMO",
                "read_only": True,
                "execution_authorized": False,
            }
        except Exception:
            try:
                self.sessions.unbind(owner, connection_id=connection_id)
            except Exception:
                pass
            try:
                self.connections.mark_disconnected(owner, connection_id=connection_id)
            except Exception:
                pass
            try:
                adapter.disconnect()
            except Exception:
                pass
            raise
