from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HealthAlert:
    component: str
    severity: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def build_health_alerts(components: dict[str, str]) -> list[HealthAlert]:
    alerts: list[HealthAlert] = []
    for component, status in components.items():
        normalized = str(status).upper()
        if normalized in {"ONLINE", "DEMO_VALIDADO", "DISABLED", "DESABILITADO", "FOUNDATION"}:
            continue
        if normalized in {"WARNING", "AGUARDANDO_FONTE", "NOT_CONFIGURED", "FUTURO_NAO_BLOQUEANTE"}:
            alerts.append(HealthAlert(component, "WARNING", normalized, f"{component}: {normalized}"))
            continue
        alerts.append(HealthAlert(component, "CRITICAL", normalized, f"{component}: {normalized}"))
    return alerts
