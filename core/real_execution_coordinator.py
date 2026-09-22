from __future__ import annotations

from dataclasses import dataclass

from core.decision_snapshot import DecisionSnapshot
from core.p117_real_admission import RealAdmissionBoundary
from core.p114_real_safety_gate import RealSafetyReport
from core.p116_real_release_audit import RealReleaseAudit
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.senior_context_cycle import SeniorContextCycle
from execution.p124_broker_session import BrokerSessionBoundary, BrokerSessionPort
from execution.real_gateway import RealExecutionGateway, RealGatewayResult, RealGatewayStatus
from execution.ports import ExecutionRequest
from core.execution_coordinator import ExecutionPlan
from core.live_orchestrator import OrchestrationResult
from core.real_safety_provider import RealSafetyProvider, read_authoritative_real_safety


@dataclass(frozen=True)
class RealExecutionCoordinator:
    """Explicit REAL-mode bridge; DEMO execution remains on its existing path."""

    gateway: RealExecutionGateway
    authorization_issuer: RealAuthorizationIssuer
    admission_boundary: RealAdmissionBoundary
    release_audit: RealReleaseAudit
    broker_session: BrokerSessionPort
    real_safety_provider: RealSafetyProvider
    broker_id: str
    adapter_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.gateway, RealExecutionGateway):
            raise ValueError("gateway REAL é obrigatório.")
        if not isinstance(self.authorization_issuer, RealAuthorizationIssuer):
            raise ValueError("authorization issuer inválido.")
        if not isinstance(self.admission_boundary, RealAdmissionBoundary):
            raise ValueError("admission boundary inválida.")
        if not isinstance(self.release_audit, RealReleaseAudit):
            raise ValueError("auditoria P116 é obrigatória.")
        if not self.release_audit.verified:
            raise ValueError("somente auditoria P116 VERIFIED pode habilitar a sessão REAL.")
        if not callable(getattr(self.broker_session, "check_session", None)):
            raise ValueError("sessão da corretora inválida.")
        if not isinstance(self.real_safety_provider, RealSafetyProvider):
            raise ValueError("provedor de segurança REAL é obrigatório.")
        for name, value in (("broker_id", self.broker_id), ("adapter_id", self.adapter_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        orchestration: OrchestrationResult,
        explicit_approval: bool,
    ) -> RealGatewayResult:
        if not isinstance(plan, ExecutionPlan):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "plano de execução inválido.")
        if not isinstance(orchestration, OrchestrationResult):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "orquestração inválida.")
        if orchestration.senior_context is None:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "contexto sênior obrigatório antes do REAL.")
        if explicit_approval is not True:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "seleção REAL exige aprovação explícita.")
        try:
            session = self.broker_session.check_session()
            if not BrokerSessionBoundary.is_usable(session):
                return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL da corretora não está autenticada.")
        except (ValueError, TypeError, RuntimeError):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL da corretora não pôde ser validada.")
        if plan.request.mode.value != "REAL":
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL recebeu um plano que não está em modo REAL.")

        request: ExecutionRequest = plan.request
        request_id = plan.request_id
        symbol = request.symbol
        try:
            current_safety: RealSafetyReport = read_authoritative_real_safety(self.real_safety_provider)
            authorization = self.authorization_issuer.issue(
                audit=self.release_audit,
                authorization_id=f"auth-{request_id}",
                audit_id=self.release_audit.audit_id,
                broker_id=self.broker_id,
                adapter_id=self.adapter_id,
                request_id=request_id,
                symbol=symbol,
                explicit_approval=True,
            )
            admission = self.admission_boundary.admit(
                admission_id=f"admission-{request_id}",
                audit_id=self.release_audit.audit_id,
                audit_verified=self.release_audit,
                authorization_active=authorization,
                safety_ready=current_safety.ready,
                broker_available=True,
                broker_id=self.broker_id,
                adapter_id=self.adapter_id,
                request_id=request_id,
                symbol=symbol,
            )
        except (ValueError, TypeError, RuntimeError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"REAL não pôde ser admitido: {type(exc).__name__}")

        return self.gateway.execute(
            broker=self.broker_id,
            request_id=request_id,
            request=request,
            authorization=authorization,
            admission=admission,
            safety=current_safety,
            snapshot=orchestration.snapshot,
        )
