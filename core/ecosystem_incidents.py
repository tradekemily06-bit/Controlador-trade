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
    """Fail-closed incident lifecycle backed by durable cross-process state."""
    def __init__(self, *, notification_center=None, store: TechnicalIncidentStore | None = None) -> None:
        if store is not None and not isinstance(store, TechnicalIncidentStore):
            raise TypeError("store inválido")
        self._notification_center = notification_center
        self._store = store
        self._incidents: dict[str, TechnicalIncident] = {}
        self._lock = RLock()

    def open_incident(self, *, title: str, message: str, incident_id: str | None = None, now: datetime | None = None) -> TechnicalIncident:
        if not isinstance(title, str) or not title.strip() or not isinstance(message, str) or not message.strip():
            raise ValueError("incident title and message are required")
        started_at = _utc(now or datetime.now(timezone.utc))
        incident = TechnicalIncident((incident_id or f"incident-{uuid4().hex}").strip(), title.strip(), message.strip(), started_at)
        with self._lock:
            if self._store is not None:
                current = self._store.status()
                if current["status"] == "INCIDENT":
                    existing_id = current.get("incident_id") or "persisted-incident"
                    if incident.incident_id != existing_id:
                        raise RuntimeError("já existe um incidente técnico ativo")
                self._store.open(incident.incident_id, f"{incident.title}: {incident.message}", now=started_at)
            self._incidents[incident.incident_id] = incident
            self._publish(incident)
        return incident

    def resolve_incident(self, incident_id: str, *, now: datetime | None = None) -> TechnicalIncident:
        key = str(incident_id).strip()
        if not key:
            raise ValueError("incident_id é obrigatório")
        with self._lock:
            current = self._incidents.get(key)
            if current is None and self._store is not None:
                state = self._store.status()
                if state["status"] == "INCIDENT":
                    persisted_id = str(state.get("incident_id") or "persisted-incident")
                    if key != persisted_id:
                        raise ValueError("incident_id não corresponde ao incidente técnico ativo")
                    current = TechnicalIncident(persisted_id, "Problema técnico ativo", str(state.get("reason") or "incidente técnico ativo"), _timestamp(state.get("changed_at")))
                    self._incidents[persisted_id] = current
            if current is None:
                raise ValueError("incident not found")
            if current.status is IncidentStatus.RESOLVED:
                return current
            resolved_at = _utc(now or datetime.now(timezone.utc))
            if self._store is not None:
                self._store.resolve(key, now=resolved_at)
            resolved = TechnicalIncident(current.incident_id, current.title, current.message, current.started_at, IncidentStatus.RESOLVED, resolved_at)
            self._incidents[key] = resolved
            if self._notification_center is not None:
                self._notification_center.publish_global(EcosystemNotification(f"incident-resolved-{uuid4().hex}", NotificationKind.RECOVERY, NotificationSeverity.IMPORTANT, "Problema técnico resolvido", f"O incidente {key} foi resolvido. O ecossistema só volta a operar se as demais barreiras de segurança também estiverem liberadas.", requires_attention=True))
            return resolved

    def active(self) -> tuple[TechnicalIncident, ...]:
        with self._lock:
            if self._store is not None:
                try:
                    state = self._store.status()
                except (OSError, ValueError, TypeError, RuntimeError):
                    return (_unavailable_state_incident(),)
                if state["status"] == "INCIDENT":
                    persisted_id = str(state.get("incident_id") or "persisted-incident")
                    local = self._incidents.get(persisted_id)
                    if local is not None and local.status is IncidentStatus.ACTIVE:
                        return (local,)
                    return (TechnicalIncident(persisted_id, "Problema técnico ativo", str(state.get("reason") or "incidente técnico ativo"), _timestamp(state.get("changed_at"))),)
                return ()
            return tuple(item for item in self._incidents.values() if item.status is IncidentStatus.ACTIVE)

    def execution_blocked(self) -> bool:
        if self._store is None:
            return bool(self.active())
        try:
            return self._store.status()["status"] != "HEALTHY"
        except (OSError, ValueError, TypeError, RuntimeError):
            return True

    def status(self) -> dict[str, object]:
        active = self.active()
        return {"status": "INCIDENT" if active else "HEALTHY", "execution_blocked": bool(active), "active_incidents": tuple(item.incident_id for item in active), "reason": active[0].message if active else None}

    def _publish(self, incident: TechnicalIncident) -> None:
        if self._notification_center is not None:
            self._notification_center.publish_global(EcosystemNotification(f"incident-open-{incident.incident_id}", NotificationKind.EXECUTION, NotificationSeverity.CRITICAL, "Problema técnico detectado", f"{incident.message} Novas ordens estão bloqueadas enquanto o problema é investigado e resolvido.", requires_attention=True, blocking=True))


def _unavailable_state_incident() -> TechnicalIncident:
    return TechnicalIncident(
        incident_id="incident-state-unavailable",
        title="Estado de incidente indisponível",
        message="O estado persistente de incidentes não pôde ser validado; a execução permanece bloqueada.",
        started_at=datetime.now(timezone.utc),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("incident timestamps must include timezone")
    return value.astimezone(timezone.utc)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        return datetime.now(timezone.utc)
    return _utc(datetime.fromisoformat(value))
