from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.execution_intent import ExecutionIntent
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_risk_reasoning import RiskKnowledgeStatus
from execution.gateway import ExecutionGateway, GatewayResult

if TYPE_CHECKING:
    from core.decision_snapshot import DecisionSnapshot


@dataclass(frozen=True)
class ExecutionIntentAdmission:
    """Admits an intent only after a complete senior contextual boundary."""

    gateway: ExecutionGateway

    def __post_init__(self) -> None:
        if self.gateway is None:
            raise ValueError("gateway é obrigatório.")

    def admit(
        self,
        intent: ExecutionIntent,
        *,
        senior_context: SeniorContextCycle | None = None,
        snapshot: DecisionSnapshot | None = None,
        entry_conditions: tuple[str, ...] = (),
    ) -> GatewayResult:
        if not isinstance(intent, ExecutionIntent):
            raise ValueError("intent inválida.")
        if not isinstance(senior_context, SeniorContextCycle):
            raise ValueError("contexto sênior obrigatório antes da admissão da intenção.")
        if senior_context.execution_authorized:
            raise ValueError("contexto sênior não pode conceder autoridade de execução.")
        if senior_context.quality is not SeniorContextQuality.COMPLETE:
            raise ValueError("contexto sênior incompleto; admissão bloqueada.")
        if senior_context.risk_assessment.execution_authorized:
            raise ValueError("avaliação sênior de risco não pode conceder autoridade de execução.")
        if senior_context.risk_assessment.status is not RiskKnowledgeStatus.ASSESSED:
            raise ValueError("risco sênior incompleto; admissão bloqueada.")

        return self.gateway.execute(
            intent.request_id,
            intent.as_execution_request(),
            snapshot=snapshot,
            timestamp=intent.created_at,
            entry_conditions=entry_conditions,
        )
