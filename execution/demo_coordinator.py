from __future__ import annotations

from dataclasses import dataclass

from core.decision_snapshot import DecisionSnapshot
from core.demo_readiness import DemoReadiness, DemoReadinessReport
from core.execution_intent import ExecutionIntent
from core.runtime_config import RuntimeConfig
from core.p23_market_data_integrity import MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_operation_assessment import SeniorOperationDisposition
from core.senior_risk_reasoning import RiskKnowledgeStatus
from execution.gateway import ExecutionGateway, GatewayResult, GatewayStatus


@dataclass(frozen=True)
class DemoExecutionResult:
    """Outcome of the P31 boundary; it never bypasses readiness or the gateway."""

    readiness: DemoReadinessReport
    gateway: GatewayResult | None

    @property
    def executed(self) -> bool:
        return self.gateway is not None and self.gateway.accepted


class DemoExecutionCoordinator:
    """Connects P30 readiness to the existing DEMO execution gateway."""

    def __init__(self, *, readiness: DemoReadiness, gateway: ExecutionGateway) -> None:
        if not isinstance(readiness, DemoReadiness):
            raise ValueError("readiness inválido.")
        if not isinstance(gateway, ExecutionGateway):
            raise ValueError("gateway inválido.")
        self.readiness = readiness
        self.gateway = gateway

    def execute(
        self,
        *,
        config: RuntimeConfig,
        market_data: MarketDataIntegrityReport,
        recovery: RecoveryAssessment,
        intent: ExecutionIntent | None,
        senior_context: SeniorContextCycle | None,
        snapshot: DecisionSnapshot | None,
    ) -> DemoExecutionResult:
        readiness = self.readiness.evaluate(
            config=config,
            market_data=market_data,
            recovery=recovery,
            intent=intent,
        )
        if not readiness.ready or intent is None:
            return DemoExecutionResult(readiness=readiness, gateway=None)

        if not isinstance(snapshot, DecisionSnapshot):
            return DemoExecutionResult(
                readiness=readiness,
                gateway=GatewayResult(GatewayStatus.BLOCKED, "snapshot de decisão obrigatório para execução DEMO."),
            )
        if not isinstance(senior_context, SeniorContextCycle):
            return DemoExecutionResult(
                readiness=readiness,
                gateway=None,
            )
        if senior_context.execution_authorized:
            return DemoExecutionResult(readiness=readiness, gateway=None)
        if senior_context.quality is not SeniorContextQuality.COMPLETE:
            return DemoExecutionResult(readiness=readiness, gateway=None)
        if senior_context.operation_assessment is None:
            return DemoExecutionResult(
                readiness=readiness,
                gateway=GatewayResult(GatewayStatus.BLOCKED, "avaliação profissional da operação ausente; execução DEMO bloqueada."),
            )
        if senior_context.operation_assessment.disposition is not SeniorOperationDisposition.SUITABLE:
            return DemoExecutionResult(
                readiness=readiness,
                gateway=GatewayResult(GatewayStatus.BLOCKED, "avaliação profissional não considera a operação adequada; execução DEMO bloqueada."),
            )
        if senior_context.risk_assessment.execution_authorized:
            return DemoExecutionResult(readiness=readiness, gateway=None)
        if senior_context.risk_assessment.status is not RiskKnowledgeStatus.ASSESSED:
            return DemoExecutionResult(readiness=readiness, gateway=None)

        # Preserve the immutable decision timestamp. Never replace an old
        # intent's creation time with the current dispatch time, otherwise a
        # stale decision could incorrectly appear fresh at the gateway.
        gateway_result = self.gateway.execute(
            intent.request_id,
            intent.as_execution_request(),
            snapshot=snapshot,
            timestamp=intent.created_at,
        )
        return DemoExecutionResult(readiness=readiness, gateway=gateway_result)
