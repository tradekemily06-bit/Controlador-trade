from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from audit.events import AuditEvent, AuditEventType, AuditLogger
from core.decision_engine import DecisionEngine, FinalDecision, DecisionResult
from core.execution_intent import ExecutionIntent
from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operational_state import OperationalState
from core.p23_market_data_integrity import MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment
from core.runtime_config import RuntimeConfig
from core.signal_quality import SignalQuality, SignalQualityEvaluator
from execution.demo_coordinator import DemoExecutionCoordinator, DemoExecutionResult
from execution.ports import ExecutionMode, ExecutionResult


@dataclass(frozen=True)
class DemoFlowResult:
    decision: DecisionResult
    execution: ExecutionResult | None
    quality: SignalQuality
    execution_result: DemoExecutionResult | None = None


class DemoFlow:
    """Orquestra análise, decisão, prontidão DEMO, execução e auditoria."""

    def __init__(self, *, decision_engine: DecisionEngine, demo_coordinator: DemoExecutionCoordinator, audit_logger: AuditLogger, quality_evaluator: SignalQualityEvaluator | None = None, request_id_factory: Callable[[], str] | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.decision_engine = decision_engine
        self.demo_coordinator = demo_coordinator
        self.audit_logger = audit_logger
        self.quality_evaluator = quality_evaluator or SignalQualityEvaluator()
        self.request_id_factory = request_id_factory or (lambda: str(uuid4()))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, *, analysis: AnalysisResult, market_context: MarketContextResult | None, operational_state: OperationalState | None, symbol: str, amount: float, duration_seconds: int, config: RuntimeConfig, market_data: MarketDataIntegrityReport, recovery: RecoveryAssessment) -> DemoFlowResult:
        quality = self.quality_evaluator.evaluate(analysis)
        self.audit_logger.record(AuditEvent(event_type=AuditEventType.ANALYSIS, message="Análise recebida pelo fluxo DEMO.", data={"signal": analysis.signal.value, "score": analysis.score, "symbol": symbol, "quality_score": quality.score, "quality_level": quality.level.value, "actionable": quality.actionable}))

        decision = self.decision_engine.evaluate(analysis=analysis, market_context=market_context, operational_state=operational_state)
        self.audit_logger.record(AuditEvent(event_type=AuditEventType.DECISION, message="Decisão registrada.", data={"decision": decision.decision, "signal": decision.signal.value, "reason": decision.reason, "quality_level": quality.level.value, "quality_score": quality.score}))

        if decision.decision != FinalDecision.EXECUTAR:
            self.audit_logger.record(AuditEvent(event_type=AuditEventType.RISK, message="Execução não autorizada.", data={"decision": decision.decision, "reason": decision.reason, "quality_level": quality.level.value}))
            return DemoFlowResult(decision=decision, execution=None, quality=quality)

        intent = ExecutionIntent(request_id=self.request_id_factory(), symbol=symbol, signal=decision.signal, amount=amount, duration_seconds=duration_seconds, mode=ExecutionMode.DEMO, created_at=self.clock())
        execution_result = self.demo_coordinator.execute(config=config, market_data=market_data, recovery=recovery, intent=intent)
        execution = execution_result.gateway.execution if execution_result.gateway is not None else None
        readiness_message = "; ".join(execution_result.readiness.reasons)
        message = execution.message if execution is not None else readiness_message

        self.audit_logger.record(AuditEvent(event_type=AuditEventType.EXECUTION, message="Resultado da execução DEMO registrado.", data={"accepted": execution is not None and execution.accepted, "external_id": execution.external_id if execution is not None else None, "message": message, "quality_level": quality.level.value, "quality_score": quality.score, "readiness": readiness_message}))
        return DemoFlowResult(decision=decision, execution=execution, quality=quality, execution_result=execution_result)
