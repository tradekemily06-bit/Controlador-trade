from __future__ import annotations

from dataclasses import dataclass

from core.decision_engine import FinalDecision
from core.live_orchestrator import OrchestrationResult
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayResult, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest


@dataclass(frozen=True)
class ExecutionPlan:
    """Plano explícito de execução derivado de uma decisão já avaliada."""

    request_id: str
    request: ExecutionRequest


class ExecutionCoordinator:
    """Liga a decisão à camada de execução sem criar uma nova estratégia."""

    def __init__(self, gateway: ExecutionGateway) -> None:
        if gateway is None:
            raise ValueError("gateway é obrigatório.")
        self.gateway = gateway

    @staticmethod
    def build_plan(
        orchestration: OrchestrationResult,
        *,
        request_id: str,
        amount: float,
        duration_seconds: int,
        mode: ExecutionMode = ExecutionMode.DEMO,
    ) -> ExecutionPlan:
        if not isinstance(orchestration, OrchestrationResult):
            raise ValueError("resultado de orquestração inválido.")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        if orchestration.decision.decision is not FinalDecision.EXECUTAR:
            raise ValueError("somente decisões EXECUTAR podem gerar plano de execução.")
        signal = Signal(orchestration.analysis.signal.value)
        symbol = orchestration.analysis.symbol
        if not symbol:
            raise ValueError("decisão executável precisa de símbolo.")
        return ExecutionPlan(
            request_id=request_id,
            request=ExecutionRequest(
                symbol=symbol,
                signal=signal,
                amount=amount,
                duration_seconds=duration_seconds,
                mode=mode,
                request_id=request_id,
            ),
        )

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        orchestration: OrchestrationResult,
        entry_conditions: tuple[str, ...] = (),
    ) -> GatewayResult:
        if not isinstance(plan, ExecutionPlan):
            return GatewayResult(GatewayStatus.INVALID_REQUEST, "plano de execução inválido.")
        return self.gateway.execute(
            plan.request_id,
            plan.request,
            snapshot=orchestration.snapshot,
            timestamp=orchestration.timestamp,
            entry_conditions=entry_conditions,
        )
