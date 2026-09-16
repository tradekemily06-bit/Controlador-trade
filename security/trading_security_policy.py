"""Layered security policy for the trading ecosystem.

This module describes and evaluates controls that belong around the broker
adapter and user session. It never stores credentials and never grants order
execution authority. Missing or unsafe controls fail closed for protected
operation readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


class SecurityReadiness(str, Enum):
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class BrokerSecurityPosture:
    """Security facts supplied by a trusted broker/infrastructure adapter."""

    mfa_enabled: bool = False
    phishing_resistant_mfa: bool = False
    api_read_enabled: bool = True
    api_trading_enabled: bool = True
    api_withdrawal_enabled: bool = False
    ip_whitelist_configured: bool = False
    ip_whitelist_match: bool = True
    address_whitelist_configured: bool = False
    address_whitelist_match: bool = True
    protective_orders_supported: bool = False
    protective_orders_active: bool = False
    broker_session_healthy: bool = False
    market_connection_healthy: bool = False
    backup_connection_available: bool = False
    dedicated_runtime: bool = False
    vps_or_hardened_runtime: bool = False
    security_incident_clear: bool = False
    security_state_available: bool = False
    active_permissions: FrozenSet[str] = frozenset({"READ", "TRADE"})


@dataclass(frozen=True)
class DeviceSessionPolicy:
    """Explicit user-session behavior for multi-device use.

    A new device does not disconnect another device. A device stays connected
    until the user explicitly disconnects it or a server-side security event
    invalidates it. This is separate from broker connectivity: a lost network
    connection can block trading without logging the user out.
    """

    allow_multiple_devices: bool = True
    connect_requires_explicit_action: bool = True
    disconnect_requires_explicit_action: bool = True
    new_device_disconnects_existing: bool = False
    network_loss_logs_user_out: bool = False
    security_event_may_revoke_sessions: bool = True


@dataclass(frozen=True)
class SecurityAssessment:
    readiness: SecurityReadiness
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    protected_operation_allowed: bool
    execution_authorized: bool = False


class TradingSecurityPolicy:
    """Evaluate layered security without ever authorizing an order."""

    def __init__(self, *, require_protective_orders: bool = True) -> None:
        self.require_protective_orders = require_protective_orders

    def assess(self, posture: BrokerSecurityPosture) -> SecurityAssessment:
        blocked: list[str] = []
        warnings: list[str] = []

        if not posture.security_state_available:
            blocked.append("estado de segurança indisponível")
        if not posture.security_incident_clear:
            blocked.append("incidente de segurança/técnico ativo ou não confirmado como resolvido")
        if not posture.mfa_enabled:
            blocked.append("MFA não está habilitado")
        elif not posture.phishing_resistant_mfa:
            warnings.append("MFA não é phishing-resistant; prefira passkey/FIDO2 quando disponível")
        if posture.api_withdrawal_enabled or "WITHDRAWAL" in posture.active_permissions:
            blocked.append("permissão de saque/withdrawal da API está habilitada")
        if not posture.api_read_enabled or not posture.api_trading_enabled:
            blocked.append("permissões mínimas de API para leitura/trading não estão disponíveis")
        if posture.ip_whitelist_configured and not posture.ip_whitelist_match:
            blocked.append("origem fora da lista branca de IP")
        if posture.address_whitelist_configured and not posture.address_whitelist_match:
            blocked.append("destino fora da lista branca de endereços")
        if not posture.broker_session_healthy:
            blocked.append("sessão da corretora não está saudável")
        if not posture.market_connection_healthy:
            blocked.append("conexão de mercado não está saudável")
        if self.require_protective_orders:
            if not posture.protective_orders_supported:
                blocked.append("corretora/adaptador não confirmou suporte a ordens protetivas")
            elif not posture.protective_orders_active:
                blocked.append("ordem protetiva não está ativa no servidor da corretora")
        if not posture.backup_connection_available:
            warnings.append("não há conectividade de contingência confirmada")
        if not posture.dedicated_runtime:
            warnings.append("runtime não está dedicado/endurecido para trading")
        if not posture.vps_or_hardened_runtime:
            warnings.append("VPS ou runtime endurecido não foi confirmado")

        readiness = SecurityReadiness.BLOCKED if blocked else (SecurityReadiness.WARNING if warnings else SecurityReadiness.READY)
        return SecurityAssessment(
            readiness=readiness,
            blocking_reasons=tuple(blocked),
            warnings=tuple(warnings),
            protected_operation_allowed=not blocked,
            execution_authorized=False,
        )

    @staticmethod
    def session_policy() -> DeviceSessionPolicy:
        return DeviceSessionPolicy()
