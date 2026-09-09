from __future__ import annotations

from dataclasses import dataclass

from core.demo_readiness import DemoReadiness, DemoReadinessReport
from core.execution_intent import ExecutionIntent
from core.runtime_config import RuntimeConfig
from core.p23_market_data_integrity import MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment
from execution.gateway import ExecutionGateway, GatewayResult


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
    ) -> DemoExecutionResult:
        readiness = self.readiness.evaluate(
            config=config,
            market_data=market_data,
            recovery=recovery,
            intent=intent,
        )
        if not readiness.ready or intent is None:
            return DemoExecutionResult(readiness=readiness, gateway=None)

        gateway_result = self.gateway.execute(
            intent.request_id,
            intent.as_execution_request(),
        )
        return DemoExecutionResult(readiness=readiness, gateway=gateway_result)
