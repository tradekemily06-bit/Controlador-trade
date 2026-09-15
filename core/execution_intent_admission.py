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

    @staticmethod
    def _snapshot_consistency_error(intent: ExecutionIntent, snapshot: "DecisionSnapshot") -> str | None:
        """Reject an intent that no longer matches the decision that produced it."""
        if not snapshot.actionable:
            return "decisão registrada como não acionável; admissão bloqueada."
        if str(snapshot.decision).upper() != "EXECUTAR":
            return "snapshot de decisão não é EXECUTAR; admissão bloqueada."
        if snapshot.symbol != intent.symbol:
            return "símbolo da intenção diverge do snapshot da decisão; admissão bloqueada."
        if snapshot.signal != intent.signal.value:
            return "sinal da intenção diverge do snapshot da decisão; admissão bloqueada."
        if snapshot.timeframe is None:
            return "timeframe da decisão indisponível; admissão bloqueada."
        return None

    def admit(
        self,
        intent: ExecutionIntent,
        *,
        senior_context: SeniorContextCycle | None = None,
        snapshot: "DecisionSnapshot | None" = None,
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
        if snapshot is not None:
            consistency_error = self._snapshot_consistency_error(intent, snapshot)
            if consistency_error is not None:
                return self.gateway.execute.__self__.GatewayResult if False else GatewayResult(  # type: ignore[attr-defined]
                    status=self.gateway.GatewayStatus.BLOCKED if False else __import__("execution.gateway", fromlist=["GatewayStatus"]).GatewayStatus.BLOCKED,
                    message=consistency_error,
                )

        return self.gateway.execute(
            intent.request_id,
            intent.as_execution_request(),
            snapshot=snapshot,
            timestamp=intent.created_at,
            entry_conditions=entry_conditions,
        )
