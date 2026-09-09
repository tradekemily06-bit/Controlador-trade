from __future__ import annotations

from dataclasses import dataclass

from core.execution_intent import ExecutionIntent
from core.unified_safety_gate import SafetyGateReport, UnifiedSafetyGate
from core.p23_market_data_integrity import MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment
from core.runtime_config import RuntimeConfig


@dataclass(frozen=True)
class DemoReadinessReport:
    ready: bool
    reasons: tuple[str, ...]


class DemoReadiness:
    """Final read-only DEMO readiness check; it never executes an intent."""

    def __init__(self, safety_gate: UnifiedSafetyGate) -> None:
        if not isinstance(safety_gate, UnifiedSafetyGate):
            raise ValueError("safety_gate inválido.")
        self.safety_gate = safety_gate

    def evaluate(
        self,
        *,
        config: RuntimeConfig,
        market_data: MarketDataIntegrityReport,
        recovery: RecoveryAssessment,
        intent: ExecutionIntent | None,
    ) -> DemoReadinessReport:
        gate: SafetyGateReport = self.safety_gate.evaluate(
            config=config,
            market_data=market_data,
            recovery=recovery,
        )
        reasons = list(gate.reasons)
        if intent is None:
            reasons.append("intenção de execução ausente")
        elif not isinstance(intent, ExecutionIntent):
            reasons.append("intenção de execução inválida")
        elif intent.mode.value != "DEMO":
            reasons.append("somente DEMO pode ficar READY")
        if not gate.ready or any(reason for reason in reasons if reason.startswith(("intenção", "somente"))):
            return DemoReadinessReport(False, tuple(reasons))
        return DemoReadinessReport(True, tuple(reasons))
