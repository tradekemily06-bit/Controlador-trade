from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p21_observability import HealthState, RuntimeHealth
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.unified_safety_gate import SafetyGateReport, SafetyGateState


class AlertSeverity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class OperationalAlert:
    code: str
    severity: AlertSeverity
    source: str
    message: str


@dataclass(frozen=True)
class OperationalAlertReport:
    alerts: tuple[OperationalAlert, ...]

    @property
    def has_critical(self) -> bool:
        return any(a.severity is AlertSeverity.CRITICAL for a in self.alerts)

    @property
    def has_warnings(self) -> bool:
        return any(a.severity is AlertSeverity.WARNING for a in self.alerts)


class OperationalAlertMonitor:
    """Converts existing safety/health reports into deterministic alerts."""

    def assess(
        self,
        runtime: RuntimeHealth,
        market: MarketDataIntegrityReport,
        safety: SafetyGateReport,
    ) -> OperationalAlertReport:
        if not isinstance(runtime, RuntimeHealth):
            raise ValueError("runtime inválido.")
        if not isinstance(market, MarketDataIntegrityReport):
            raise ValueError("market inválido.")
        if not isinstance(safety, SafetyGateReport):
            raise ValueError("safety inválido.")

        alerts: list[OperationalAlert] = []

        if runtime.state is HealthState.BLOCKED:
            alerts.append(OperationalAlert(
                "RUNTIME_BLOCKED", AlertSeverity.CRITICAL, "runtime", runtime.message
            ))
        elif runtime.state is HealthState.ATTENTION:
            alerts.append(OperationalAlert(
                "RUNTIME_ATTENTION", AlertSeverity.WARNING, "runtime", runtime.message
            ))

        if market.health is MarketDataHealth.INVALID:
            alerts.append(OperationalAlert(
                "MARKET_DATA_INVALID", AlertSeverity.CRITICAL, "market_data", market.message
            ))
        elif market.health in (MarketDataHealth.STALE, MarketDataHealth.GAP):
            alerts.append(OperationalAlert(
                "MARKET_DATA_DEGRADED", AlertSeverity.WARNING, "market_data", market.message
            ))

        if safety.state is SafetyGateState.NOT_READY:
            message = "; ".join(safety.reasons) or "prontidão não autorizada"
            severity = AlertSeverity.CRITICAL
            alerts.append(OperationalAlert(
                "SAFETY_NOT_READY", severity, "safety_gate", message
            ))

        return OperationalAlertReport(tuple(alerts))
