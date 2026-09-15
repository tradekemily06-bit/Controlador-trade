"""Fail-closed lifecycle for unexpected technical incidents."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from uuid import uuid4

from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from core.technical_incident_store import TechnicalIncidentStore


class IncidentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True)
class TechnicalIncident:
    incident_id: str
    title: str
    message: str
    started_at: datetime
    status: IncidentStatus = IncidentStatus.ACTIVE
    resolved_at: datetime | None = None

    @property
    def execution_blocked(self) -> bool:
        return self.status is IncidentStatus.ACTIVE


class EcosystemIncidentManager:
    """Fail-closed incident barrier with optional cross-process persistence."""
    def __init__(self, *, notification_center=None, store: TechnicalIncidentStore | None = None) -> None:
        if store is not None and not isinstance(store, TechnicalIncidentStore):
            raise TypeError("store inválido")
        self._notification_center = notification_center
        self._store = store
        self._incidents: dict[str, TechnicalIncident] = {}
        self._lock = RLock()

    def open_incident(self, *, title: str, message: str, incident_id: str | None = None, now: datetime | None = None) -> TechnicalIncident:
        if not title.strip() or not message.strip():
            raise ValueError("incident title and message are required")
        started_at = _utc(now or datetime.now(timezone.utc))
        incident = TechnicalIncident((incident_id or f"incident-{uuid4().hex}").strip(), title.strip(), message.strip(), started_at)
        with self._lock:
            if self._store is not None:
                self._store.open(f"{incident.title}: {incident.message}", now=started_at)
            self._incidents[incident.incident_id] = incident
            self._publish(incident)
        return incident

    def resolve_incident(self, incident_id: str, *, now: datetime | None = None) -> TechnicalIncident:
        with self._lock:
            current = self._incidents.get(incident_id)
            if current is None:
                raise ValueError("incident not found")
            if current.status is IncidentStatus.RESOLVED:
                return current
            resolved_at = _utc(now or datetime.now(timezone.utc))
            if self._store is not None:
                self._store.resolve(now=resolved_at)
            resolved = TechnicalIncident(current.incident_id, current.title, current.message, current.started_at, IncidentStatus.RESOLVED, resolved_at)
            self._incidents[incident_id] = resolved
            if self._notification_center is not None:
                self._notification_center.publish(EcosystemNotification(f"incident-resolved-{uuid4().hex}", NotificationKind.RECOVERY, NotificationSeverity.IMPORTANT, "Problema técnico resolvido", f"O incidente {incident_id} foi resolvido. O ecossistema só volta a operar se as demais barreiras de segurança também estiverem liberadas.", requires_attention=True))
            return resolved

    def active(self) -> tuple[TechnicalIncident, ...]:
        with self._lock:
            if self._store is not None:
                state = self._store.status()
                if state["status"] == "INCIDENT":
                    local = tuple(item for item in self._incidents.values() if item.status is IncidentStatus.ACTIVE)
                    if local:
                        return local
                    return (TechnicalIncident("persisted-incident", "Problema técnico ativo", str(state.get("reason") or "incidente técnico ativo"), _timestamp(state.get("changed_at"))),)
                return ()
            return tuple(item for item in self._incidents.values() if item.status is IncidentStatus.ACTIVE)

    def execution_blocked(self) -> bool:
        if self._store is None:
            return bool(self.active())
        try:
            return self._store.status()["status"] != "HEALTHY"
        except (OSError, ValueError, TypeError):
            return True

    def status(self) -> dict[str, object]:
        try:
            active = self.active()
        except (OSError, ValueError, TypeError):
            return {"status": "INCIDENT", "execution_blocked": True, "active_incidents": (), "reason": "estado de incidente indisponível"}
        return {"status": "INCIDENT" if active else "HEALTHY", "execution_blocked": bool(active), "active_incidents": tuple(item.incident_id for item in active)}

    def _publish(self, incident: TechnicalIncident) -> None:
        if self._notification_center is not None:
            self._notification_center.publish(EcosystemNotification(f"incident-open-{incident.incident_id}", NotificationKind.EXECUTION, NotificationSeverity.CRITICAL, "Problema técnico detectado", f"{incident.message} Novas ordens estão bloqueadas enquanto o problema é investigado e resolvido.", requires_attention=True, blocking=True))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("incident timestamps must include timezone")
    return value.astimezone(timezone.utc)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        return datetime.now(timezone.utc)
    return _utc(datetime.fromisoformat(value))
