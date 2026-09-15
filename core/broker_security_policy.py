"""Security policy checks for broker integrations.

These policies are deliberately separate from execution authorization. They
state what a broker connection is allowed to expose and what production
execution would require; a passing policy never means that an order may be
sent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrokerPermission(str, Enum):
    READ = "READ"
    TRADE = "TRADE"
    WITHDRAWAL = "WITHDRAWAL"


class MfaMethod(str, Enum):
    AUTHENTICATOR = "AUTHENTICATOR"
    SECURITY_KEY = "SECURITY_KEY"
    SMS = "SMS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BrokerSecurityAssessment:
    allowed: bool
    reasons: tuple[str, ...]
    execution_authorized: bool = False


class BrokerSecurityPolicy:
    """Fail-closed baseline for broker/API connections."""

    def assess_api_permissions(self, permissions: set[BrokerPermission] | frozenset[BrokerPermission]) -> BrokerSecurityAssessment:
        normalized = frozenset(permissions)
        reasons: list[str] = []
        if BrokerPermission.WITHDRAWAL in normalized:
            reasons.append("permissão de saque/withdrawal nunca é permitida pelo ecossistema")
        if BrokerPermission.READ not in normalized:
            reasons.append("permissão de leitura de mercado/conta é obrigatória")
        if BrokerPermission.TRADE not in normalized:
            reasons.append("permissão de trading é obrigatória para uma conexão operacional")
        return BrokerSecurityAssessment(not reasons, tuple(reasons), execution_authorized=False)

    def assess_account_mfa(self, method: MfaMethod | str | None, *, production: bool) -> BrokerSecurityAssessment:
        if not production:
            return BrokerSecurityAssessment(True, (), False)
        try:
            normalized = method if isinstance(method, MfaMethod) else MfaMethod(str(method or "").upper())
        except ValueError:
            normalized = MfaMethod.UNKNOWN
        if normalized in (MfaMethod.AUTHENTICATOR, MfaMethod.SECURITY_KEY):
            return BrokerSecurityAssessment(True, (), False)
        if normalized is MfaMethod.SMS:
            return BrokerSecurityAssessment(False, ("SMS isolado não satisfaz a política MFA de produção",), False)
        return BrokerSecurityAssessment(False, ("MFA forte não foi comprovado",), False)

    def assess_protection_orders(self, *, production: bool, broker_side_protection_confirmed: bool) -> BrokerSecurityAssessment:
        if not production:
            return BrokerSecurityAssessment(True, (), False)
        if broker_side_protection_confirmed:
            return BrokerSecurityAssessment(True, (), False)
        return BrokerSecurityAssessment(False, ("proteção da posição deve estar registrada no lado da corretora antes da operação de produção",), False)

    def assess_ip_policy(self, *, source_ip: str | None, allowed_ips: set[str] | frozenset[str] | None, enforce: bool) -> BrokerSecurityAssessment:
        if not enforce:
            return BrokerSecurityAssessment(True, (), False)
        ip = str(source_ip or "").strip()
        allowlist = frozenset(str(item).strip() for item in (allowed_ips or ()) if str(item).strip())
        if not ip or not allowlist:
            return BrokerSecurityAssessment(False, ("política de IP está ativada, mas não há uma origem e allowlist válidas",), False)
        if ip not in allowlist:
            return BrokerSecurityAssessment(False, ("origem de rede não está na allowlist",), False)
        return BrokerSecurityAssessment(True, (), False)
