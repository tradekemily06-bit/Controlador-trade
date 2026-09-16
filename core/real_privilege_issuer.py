from __future__ import annotations

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyReport
from core.p116_real_release_audit import RealReleaseAudit
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.ports import ExecutionMode, ExecutionRequest


class RealPrivilegeIssuer:
    """Single authoritative issuance boundary for active REAL privileges."""

    def __init__(self, adapter_gateway: BrokerAdapterGateway) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway autoritativo é obrigatório.")
        self._adapter_gateway = adapter_gateway
        self._admission_boundary = RealAdmissionBoundary()

    def issue_authorization(
        self, *, authorization_id: str, audit_id: str,
        request_id: str, symbol: str, broker_id: str,
        audit_verified: bool, explicitly_enabled: bool,
        real_execution_allowed: bool,
    ) -> RealExecutionAuthorization:
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
        adapter_id = self._adapter_gateway.adapter_id(broker_id)
        return RealExecutionAuthorization._issue(
            authorization_id=authorization_id,
            audit_id=audit_id,
            broker_id=broker_id,
            adapter_id=adapter_id,
            request_id=request_id,
            symbol=symbol,
        )

    def issue_admission(
        self, *, admission_id: str, authorization: RealExecutionAuthorization,
        audit_verified: bool, safety: RealSafetyReport,
    ) -> RealAdmission:
        if not isinstance(authorization, RealExecutionAuthorization) or not authorization.active:
            raise PermissionError("admissão REAL exige autorização ativa emitida pela autoridade REAL.")
        if not isinstance(safety, RealSafetyReport) or not safety.ready:
            raise PermissionError("segurança REAL não está pronta")
        if not isinstance(audit_verified, bool) or not audit_verified:
            raise PermissionError("auditoria REAL não verificada")
        resolved_adapter_id = self._adapter_gateway.adapter_id(authorization.broker_id)
        if resolved_adapter_id.strip() != authorization.adapter_id.strip():
            raise PermissionError("adapter autorizado não corresponde ao adapter resolvido.")
        return self._admission_boundary._issue(
            admission_id=admission_id,
            audit_id=authorization.audit_id,
            audit_verified=True,
            authorization=authorization,
            safety_ready=safety.ready,
            broker_available=True,
        )
