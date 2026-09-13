from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class OperationalIncident:
    code: str
    severity: str
    status: str
    source: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def build_operational_incidents(observability: Mapping[str, Any]) -> list[OperationalIncident]:
    """Interpret read-only runtime observations as deterministic incidents.

    This boundary never changes runtime state, executes work, retries providers,
    or sends notifications. Missing/invalid observations fail closed.
    """
    if not isinstance(observability, Mapping):
        return [
            OperationalIncident(
                code="OPERATIONAL_INPUT_INVALID",
                severity="CRITICAL",
                status="INVALID",
                source="operational_observability",
                message="observabilidade operacional inválida",
            )
        ]

    incidents: list[OperationalIncident] = []
    execution = observability.get("execution")
    recovery = observability.get("recovery")
    reconciliation = observability.get("reconciliation")
    kill_switch = observability.get("kill_switch")
    runtime_health = observability.get("runtime_health")
    market_data = observability.get("market_data")

    if not all(isinstance(section, Mapping) for section in (execution, recovery, reconciliation, kill_switch, runtime_health, market_data)):
        return [
            OperationalIncident(
                code="OPERATIONAL_OBSERVABILITY_INCOMPLETE",
                severity="CRITICAL",
                status="INVALID",
                source="operational_observability",
                message="observabilidade operacional incompleta",
            )
        ]

    if str(execution.get("state", "BLOCKED")).upper() == "BLOCKED":
        incidents.append(
            OperationalIncident(
                code="EXECUTION_BLOCKED",
                severity="CRITICAL",
                status="BLOCKED",
                source="execution",
                message="execução bloqueada pelo estado operacional",
            )
        )

    if bool(kill_switch.get("enabled", False)):
        incidents.append(
            OperationalIncident(
                code="KILL_SWITCH_ACTIVE",
                severity="CRITICAL",
                status="ACTIVE",
                source="kill_switch",
                message="kill switch ativo; execução permanece bloqueada",
            )
        )

    recovery_state = str(recovery.get("state", "NOT_CONNECTED")).upper()
    if recovery_state in {"INVALID", "NOT_CONNECTED"}:
        incidents.append(
            OperationalIncident(
                code="RECOVERY_UNSAFE",
                severity="CRITICAL",
                status=recovery_state,
                source="recovery",
                message=f"recovery não está seguro: {recovery_state}",
            )
        )
    elif recovery_state == "REQUIRES_RECONCILIATION":
        incidents.append(
            OperationalIncident(
                code="RECONCILIATION_REQUIRED",
                severity="WARNING",
                status=recovery_state,
                source="recovery",
                message="reconciliação é necessária antes de retomar",
            )
        )

    if reconciliation.get("pending_request_ids") or reconciliation.get("unknown_request_ids"):
        incidents.append(
            OperationalIncident(
                code="EXECUTION_RECONCILIATION_PENDING",
                severity="WARNING",
                status="PENDING",
                source="reconciliation",
                message="existem operações pendentes ou com resultado desconhecido",
            )
        )

    runtime_state = str(runtime_health.get("state", "BLOCKED")).upper()
    if runtime_state == "BLOCKED":
        incidents.append(
            OperationalIncident(
                code="RUNTIME_HEALTH_BLOCKED",
                severity="CRITICAL",
                status=runtime_state,
                source="runtime_health",
                message="monitoramento do runtime indica estado BLOCKED",
            )
        )
    elif runtime_state == "ATTENTION":
        incidents.append(
            OperationalIncident(
                code="RUNTIME_HEALTH_ATTENTION",
                severity="WARNING",
                status=runtime_state,
                source="runtime_health",
                message="monitoramento do runtime requer atenção",
            )
        )

    market_state = str(market_data.get("health", "NOT_CONNECTED")).upper()
    if market_state in {"INVALID", "NOT_CONNECTED", "UNKNOWN"}:
        incidents.append(
            OperationalIncident(
                code="MARKET_DATA_UNSAFE",
                severity="CRITICAL",
                status=market_state,
                source="market_data",
                message=f"dados de mercado não estão seguros para análise: {market_state}",
            )
        )
    elif market_state in {"STALE", "GAP"}:
        incidents.append(
            OperationalIncident(
                code="MARKET_DATA_DEGRADED",
                severity="WARNING",
                status=market_state,
                source="market_data",
                message=f"integridade de mercado degradada: {market_state}",
            )
        )

    return incidents
