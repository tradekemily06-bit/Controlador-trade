from __future__ import annotations

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary
from core.p114_real_safety_gate import RealSafetyReport
from execution.broker_registry import BrokerRegistry


class RealPrivilegeIssuer:
    """Single issuance boundary for active REAL authorization and admission."""

    def __init__(self, registry: BrokerRegistry) -> None:
        if not isinstance(registry, BrokerRegistry):
            raise ValueError("registry de corretoras é obrigatório.")
        self._registry = registry
        self._admission_boundary = RealAdmissionBoundary()

    def issue_authorization(self, *, authorization_id: str, audit_id: str,
                            request_id: str, symbol: str, broker_id: str,
                            audit_verified: bool, explicitly_enabled: bool,
                            real_execution_allowed: bool) -> RealExecutionAuthorization:
        if not all(isinstance(value, str) and value.strip() for value in (
            authorization_id, audit_id, request_id, symbol, broker_id,
        )):
            raise ValueError("identidade REAL incompleta.")
        if not all(isinstance(value, bool) for value in (
            audit_verified, explicitly_enabled, real_execution_allowed,
        )):
            raise TypeError("estado de emissão REAL inválido.")
        if not audit_verified:
            raise PermissionError("auditoria REAL não verificada; emissão bloqueada")
        if not explicitly_enabled or not real_execution_allowed:
            raise PermissionError("habilitação REAL explícita não concedida")
        adapter_id = self._registry.adapter_id(broker_id)
        return RealExecutionAuthorization(
            authorization_id, audit_id, broker_id, adapter_id,
            request_id, symbol, True, True,
        )

    def issue_admission(self, *, admission_id: str,
                        authorization: RealExecutionAuthorization,
                        audit_verified: bool,
                        safety: RealSafetyReport) -> RealAdmission:
        if not isinstance(authorization, RealExecutionAuthorization) or not authorization.active:
            raise PermissionError("autorização REAL ativa é obrigatória")
        if not isinstance(safety, RealSafetyReport) or not safety.ready:
            raise PermissionError("segurança REAL não está pronta")
        if not isinstance(audit_verified, bool) or not audit_verified:
            raise PermissionError("auditoria REAL não verificada")
        resolved_adapter_id = self._registry.adapter_id(authorization.broker_id)
        if resolved_adapter_id != authorization.adapter_id:
            raise PermissionError("adapter_id autorizado não corresponde ao registry")
        return self._admission_boundary.admit(
            admission_id=admission_id,
            audit_id=authorization.audit_id,
            audit_verified=True,
            authorization_active=True,
            safety_ready=True,
            broker_available=True,
            broker_id=authorization.broker_id,
            adapter_id=resolved_adapter_id,
            request_id=authorization.request_id,
            symbol=authorization.symbol,
        )
