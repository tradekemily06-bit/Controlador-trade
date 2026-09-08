from __future__ import annotations

from dataclasses import dataclass

from audit.events import AuditEvent, AuditEventType, AuditLogger
from core.decision_engine import DecisionEngine, FinalDecision, DecisionResult
from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operational_state import OperationalState
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


@dataclass(frozen=True)
class DemoFlowResult:
    decision: DecisionResult
    execution: ExecutionResult | None


class DemoFlow:
    """Orquestra análise, decisão, execução DEMO e auditoria."""

    def __init__(
        self,
        *,
        decision_engine: DecisionEngine,
        paper_executor: PaperExecutor,
        audit_logger: AuditLogger,
    ) -> None:
        self.decision_engine = decision_engine
        self.paper_executor = paper_executor
        self.audit_logger = audit_logger

    def run(
        self,
        *,
        analysis: AnalysisResult,
        market_context: MarketContextResult | None,
        operational_state: OperationalState | None,
        symbol: str,
        amount: float,
        duration_seconds: int,
    ) -> DemoFlowResult:
        self.audit_logger.record(
            AuditEvent(
                event_type=AuditEventType.ANALYSIS,
                message="Análise recebida pelo fluxo DEMO.",
                data={
                    "signal": analysis.signal.value,
                    "score": analysis.score,
                    "symbol": symbol,
                },
            )
        )

        decision = self.decision_engine.evaluate(
            analysis=analysis,
            market_context=market_context,
            operational_state=operational_state,
        )

        self.audit_logger.record(
            AuditEvent(
                event_type=AuditEventType.DECISION,
                message="Decisão registrada.",
                data={
                    "decision": decision.decision,
                    "signal": decision.signal.value,
                    "reason": decision.reason,
                },
            )
        )

        if decision.decision != FinalDecision.EXECUTAR:
            self.audit_logger.record(
                AuditEvent(
                    event_type=AuditEventType.RISK,
                    message="Execução não autorizada.",
                    data={
                        "decision": decision.decision,
                        "reason": decision.reason,
                    },
                )
            )
            return DemoFlowResult(
                decision=decision,
                execution=None,
            )

        request = ExecutionRequest(
            symbol=symbol,
            signal=analysis.signal,
            amount=amount,
            duration_seconds=duration_seconds,
            mode=ExecutionMode.DEMO,
        )

        execution = self.paper_executor.execute(request)

        self.audit_logger.record(
            AuditEvent(
                event_type=AuditEventType.EXECUTION,
                message="Resultado da execução DEMO registrado.",
                data={
                    "accepted": execution.accepted,
                    "external_id": execution.external_id,
                    "message": execution.message,
                },
            )
        )

        return DemoFlowResult(
            decision=decision,
            execution=execution,
        )
