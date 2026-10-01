from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.kill_switch import KillSwitch
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.runtime_config import RuntimeConfig
from execution.ports import ExecutionMode


class SafetyGateState(str, Enum):
    NOT_READY = "NOT_READY"
    READY_DEMO = "READY_DEMO"
    READY_REAL = "READY_REAL"


@dataclass(frozen=True)
class SafetyGateReport:
    state: SafetyGateState
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.state in (SafetyGateState.READY_DEMO, SafetyGateState.READY_REAL)


class UnifiedSafetyGate:
    """Read-only composition of configuration, market data and recovery checks."""

    def __init__(self, *, kill_switch: KillSwitch) -> None:
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch inválido.")
        self.kill_switch = kill_switch

    def evaluate(
        self,
        *,
        config: RuntimeConfig,
        market_data: MarketDataIntegrityReport,
        recovery: RecoveryAssessment,
    ) -> SafetyGateReport:
        reasons: list[str] = []
        if not isinstance(config, RuntimeConfig):
            return SafetyGateReport(SafetyGateState.NOT_READY, ("configuração inválida",))
        if not isinstance(market_data, MarketDataIntegrityReport):
            return SafetyGateReport(SafetyGateState.NOT_READY, ("integridade de dados inválida",))
        if not isinstance(recovery, RecoveryAssessment):
            return SafetyGateReport(SafetyGateState.NOT_READY, ("avaliação de recovery inválida",))
        if config.mode is ExecutionMode.REAL and not config.real_enabled:
            reasons.append("REAL não está explicitamente habilitado na configuração")
        if not self.kill_switch.allows_execution():
            reasons.append("kill switch ativo")
        if market_data.health is not MarketDataHealth.HEALTHY:
            reasons.append(f"dados de mercado não estão HEALTHY: {market_data.health.value}")
        if market_data.stale or market_data.gap_count:
            reasons.append("relatório de integridade de dados inconsistente")
        if recovery.state not in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME):
            reasons.append(f"recovery não está seguro: {recovery.state.value}")
        if reasons:
            return SafetyGateReport(SafetyGateState.NOT_READY, tuple(reasons))
        if config.mode is ExecutionMode.REAL:
            return SafetyGateReport(
                SafetyGateState.READY_REAL,
                ("segurança estrutural REAL pronta; autorização, admissão, risco e confirmação humana continuam obrigatórios.",),
            )
        return SafetyGateReport(SafetyGateState.READY_DEMO, ("todas as condições de segurança DEMO estão satisfeitas",))
