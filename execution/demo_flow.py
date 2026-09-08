from __future__ import annotations

from dataclasses import dataclass

from audit.events import AuditEvent, AuditEventType, AuditLogger
from core.decision_engine import DecisionEngine, FinalDecision, DecisionResult
from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operational_state import OperationalState
from core.signal_quality import SignalQuality, SignalQualityEvaluator
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


@dataclass(frozen=True)
class DemoFlowResult:
    decision: DecisionResult
    execution: ExecutionResult | None
    quality: SignalQuality


class DemoFlow:
    """Orquestra análise, decisão, qualidade, execução DEMO e auditoria."""

    def __init__(
        self,
        *,
        decision_engine: DecisionEngine,
        paper_executor: PaperExecutor,
        audit_logger: AuditLogger,
        quality_evaluator: SignalQualityEvaluator | None = None,
    ) -> None:
        self.decision_engine = decision_engine
        self.paper_executor = paper_executor
        self.audit_logger = audit_logger
        self.quality_evaluator = quality_evaluator or SignalQualityEvaluator()

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
        quality = self.quality_evaluator.evaluate(analysis)

        self.audit_logger.record(
            AuditEvent(
                event_type=AuditEventType.ANALYSIS,
                message="Análise recebida pelo fluxo DEMO.",
                data={
                    "signal": analysis.signal.value,
                    "score": analysis.score,
                    "symbol": symbol,
                    "quality_score": quality.score,
                    "quality_level": quality.level.value,
                    "actionable": quality.actionable,
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
                    "quality_level": quality.level.value,
                    "quality_score": quality.score,
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
                        "quality_level": quality.level.value,
                    },
                )
            )
            return DemoFlowResult(
                decision=decision,
                execution=None,
                quality=quality,
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
                    "quality_level": quality.level.value,
                    "quality_score": quality.score,
                },
            )
        )

        return DemoFlowResult(
            decision=decision,
            execution=execution,
            quality=quality,
        )
