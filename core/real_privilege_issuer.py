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
        self, *, authorization_id: str, release_audit: RealReleaseAudit,
        broker: str, request: ExecutionRequest,
        explicit_real_enablement: bool,
    ) -> RealExecutionAuthorization:
        if not isinstance(release_audit, RealReleaseAudit) or not release_audit.verified:
            raise PermissionError("autorização REAL exige auditoria de release verificada.")
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            raise PermissionError("autorização REAL exige requisição REAL.")
        if not isinstance(explicit_real_enablement, bool) or not explicit_real_enablement:
            raise PermissionError("emissão REAL exige habilitação explícita.")
        if not isinstance(broker, str) or not broker.strip():
            raise ValueError("broker é obrigatório.")
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            raise ValueError("request_id da requisição REAL é obrigatório.")
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            raise ValueError("symbol da requisição REAL é obrigatório.")
        adapter_id = self._adapter_gateway.adapter_id(broker)
        return RealExecutionAuthorization._issue(
            authorization_id=authorization_id,
            audit_id=release_audit.audit_id,
            broker_id=broker,
            adapter_id=adapter_id,
            request_id=request.request_id,
            symbol=request.symbol,
        )

    def issue_admission(
        self, *, admission_id: str, authorization: RealExecutionAuthorization,
        release_audit: RealReleaseAudit, safety: RealSafetyReport,
        broker_available: bool,
    ) -> RealAdmission:
        if not isinstance(authorization, RealExecutionAuthorization) or not authorization.active:
            raise PermissionError("admissão REAL exige autorização ativa emitida pela autoridade REAL.")
        if not isinstance(release_audit, RealReleaseAudit) or not release_audit.verified:
            raise PermissionError("admissão REAL exige auditoria de release verificada.")
        if authorization.audit_id != release_audit.audit_id:
            raise PermissionError("auditoria da autorização REAL não corresponde ao release auditado.")
        if not isinstance(safety, RealSafetyReport):
            raise ValueError("segurança REAL inválida.")
        if not isinstance(broker_available, bool):
            raise TypeError("broker_available deve ser booleano.")
        resolved_adapter_id = self._adapter_gateway.adapter_id(authorization.broker_id)
        if resolved_adapter_id.strip() != authorization.adapter_id.strip():
            raise PermissionError("adapter autorizado não corresponde ao adapter resolvido.")
        return self._admission_boundary._issue(
            admission_id=admission_id,
            audit_id=release_audit.audit_id,
            audit_verified=True,
            authorization=authorization,
            safety_ready=safety.ready,
            broker_available=broker_available,
        )
