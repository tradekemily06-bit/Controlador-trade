"""Trusted provider onboarding orchestration without persisting credentials.

The secret resolver and provider factories are injected by the host. This
module stores only account metadata and binds a server-side read-only adapter
after an actual provider handshake.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context
from security.tenant_provider_connections import TenantProviderConnectionRegistry
from integration.tenant_market_data_sessions import TenantMarketDataSessionRegistry


_CREDENTIAL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


@dataclass(frozen=True)
class ProviderHandshake:
    provider_id: str
    account_reference: str
    capabilities: tuple[str, ...]
    verified: bool


class TenantProviderConnectionService:
    """Connect/disconnect accounts using host-owned secret and adapter services.

    A browser may submit a credential reference, never a credential value.
    The host resolver enforces tenant ownership of that reference.
    """

    def __init__(
        self,
        connections: TenantProviderConnectionRegistry,
        sessions: TenantMarketDataSessionRegistry,
        *,
        secret_resolver: Any | None = None,
        adapter_factories: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None,
    ) -> None:
        if connections is None or sessions is None:
            raise ValueError("connection and session registries are required")
        if secret_resolver is not None and not callable(getattr(secret_resolver, "resolve", None)):
            raise ValueError("tenant secret resolver must implement resolve(context, reference)")
        if adapter_factories is not None and not isinstance(adapter_factories, Mapping):
            raise ValueError("adapter_factories deve ser um mapeamento confiável")
        if bool(secret_resolver) != bool(adapter_factories):
            raise ValueError("secret resolver e adapter factories devem ser provisionados juntos")
        self.connections = connections
        self.sessions = sessions
        self.secret_resolver = secret_resolver
        self.adapter_factories = dict(adapter_factories or {})
        for provider_id, factory in self.adapter_factories.items():
            if not isinstance(provider_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", provider_id):
                raise ValueError("provider_id inválido")
            if not callable(factory):
                raise ValueError("provider adapter factory must be callable")

    def connect(
        self,
        context: TenantContext | None,
        *,
        provider_id: str,
        account_alias: str,
        credential_ref: str,
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        if self.secret_resolver is None or not self.adapter_factories:
            raise RuntimeError("cofre de credenciais e factories de provedores não provisionados")
        if provider_id not in self.adapter_factories:
            raise ValueError("provider não habilitado neste servidor")
        if not isinstance(credential_ref, str) or not _CREDENTIAL_REF.fullmatch(credential_ref):
            raise ValueError("credential_ref inválida; envie uma referência do cofre, nunca o segredo")
        if not isinstance(account_alias, str) or not account_alias.strip() or len(account_alias.strip()) > 80:
            raise ValueError("account_alias deve conter de 1 a 80 caracteres")

        # Resolve only inside the authenticated tenant scope. Never persist,
        # return, or log the resolved credential material.
        credentials = self.secret_resolver.resolve(owner, credential_ref)
        if not isinstance(credentials, Mapping) or not credentials:
            raise PermissionError("referência de credencial não resolvida para esta identidade")

        adapter = None
        connection = None
        try:
            adapter = self.adapter_factories[provider_id](credentials)
            if adapter is None or not callable(getattr(adapter, "fetch", None)):
                raise ValueError("adapter deve implementar fetch(request)")
            connect = getattr(adapter, "connect", None)
            if callable(connect):
                connect()
            handshake_method = getattr(adapter, "handshake", None)
            if not callable(handshake_method):
                raise PermissionError("adapter sem handshake verificável")
            raw = handshake_method()
            if isinstance(raw, ProviderHandshake):
                handshake = raw
            elif isinstance(raw, dict):
                handshake = ProviderHandshake(
                    provider_id=raw.get("provider_id"),
                    account_reference=raw.get("account_reference"),
                    capabilities=tuple(raw.get("capabilities") or ()),
                    verified=raw.get("verified") is True,
                )
            else:
                raise PermissionError("resposta de handshake inválida")
            if handshake.verified is not True or handshake.provider_id != provider_id:
                raise PermissionError("handshake não confirmou o provedor solicitado")
            if not isinstance(handshake.account_reference, str) or not handshake.account_reference.strip() or len(handshake.account_reference.strip()) > 120:
                raise ValueError("account_reference inválida")
            clean_capabilities = list(handshake.capabilities)
            if any(not isinstance(item, str) for item in clean_capabilities):
                raise ValueError("capabilities do handshake inválidas")

            connection = self.connections.record_verified_connection(
                owner,
                provider_id=provider_id,
                account_alias=account_alias,
                account_reference=handshake.account_reference,
                capabilities=clean_capabilities,
                adapter_verified=True,
            )
            session = self.sessions.bind(
                owner,
                connection_id=connection["connection_id"],
                adapter=adapter,
                source=f"{provider_id}:{connection['connection_id']}",
                handshake_verified=True,
            )
            return {
                **connection,
                "adapter_status": session["status"],
                "read_only": True,
                "execution_authorized": False,
            }
        except Exception:
            if connection is not None:
                try:
                    self.connections.mark_disconnected(
                        owner, connection_id=connection["connection_id"]
                    )
                except Exception:
                    pass
            close = getattr(adapter, "disconnect", None) or getattr(adapter, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            raise

    def disconnect(
        self, context: TenantContext | None, *, connection_id: str
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        session = self.sessions.get(owner, connection_id=connection_id)
        if session is None:
            # A process restart intentionally discards adapter objects. The
            # owner must still be able to revoke stale CONNECTED metadata.
            owned = any(
                item["connection_id"] == connection_id
                for item in self.connections.list_connections(owner)
            )
            if not owned:
                return {"disconnected": False, "status": "NOT_BOUND", "execution_authorized": False}
            marked = self.connections.mark_disconnected(owner, connection_id=connection_id)
            return {
                "disconnected": bool(marked),
                "status": "DISCONNECTED_SESSION_NOT_BOUND" if marked else "NOT_BOUND",
                "execution_authorized": False,
            }
        error = None
        close = getattr(session.adapter, "disconnect", None) or getattr(session.adapter, "close", None)
        try:
            if callable(close):
                close()
        except Exception as exc:
            error = type(exc).__name__
        finally:
            self.sessions.unbind(owner, connection_id=connection_id)
            self.connections.mark_disconnected(owner, connection_id=connection_id)
        if error:
            return {
                "disconnected": True,
                "status": "DISCONNECTED_WITH_ADAPTER_CLOSE_ERROR",
                "error_class": error,
                "execution_authorized": False,
            }
        return {"disconnected": True, "status": "DISCONNECTED", "execution_authorized": False}


    def reconnect_saved(
        self, context: TenantContext | None, *, connection_id: str,
    ) -> dict[str, Any]:
        """Rebuild a saved session with fresh secret resolution and provider handshake."""
        owner = require_tenant_context(context)
        account = next(
            (item for item in self.connections.list_connections(owner)
             if item["connection_id"] == connection_id),
            None,
        )
        if account is None:
            raise PermissionError("connection does not belong to this tenant and subject")
        # Fail closed: stale CONNECTED metadata is cleared before reconnect.
        self.connections.mark_disconnected(owner, connection_id=connection_id)
        credential_ref = self.connections.get_credential_reference(
            owner, connection_id=connection_id
        )
        if credential_ref is None:
            raise RuntimeError("referência do cofre não disponível; reconexão exige novo provisionamento")
        return self.connect(
            owner,
            provider_id=account["provider_id"],
            account_alias=account["account_alias"],
            credential_ref=credential_ref,
        )
