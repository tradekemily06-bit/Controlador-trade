"""Fail-closed lifecycle for unexpected technical incidents.

An incident is distinct from planned maintenance: it represents an unexpected
technical condition detected at runtime. Active incidents block new execution,
publish a user-visible notification when a notification center is supplied,
and remain active until an explicit recovery/resolve action is recorded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from uuid import uuid4

from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity


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
    """Small fail-closed incident barrier for the execution boundary.

    The manager is intentionally conservative: opening an incident always
    blocks new execution. Resolving one requires an explicit call; there is no
    automatic recovery that could silently re-enable order dispatch.
    """

    def __init__(self, *, notification_center=None) -> None:
        self._notification_center = notification_center
        self._incidents: dict[str, TechnicalIncident] = {}
        self._lock = RLock()

    def open_incident(self, *, title: str, message: str, incident_id: str | None = None, now: datetime | None = None) -> TechnicalIncident:
        if not title.strip() or not message.strip():
            raise ValueError("incident title and message are required")
        started_at = _utc(now or datetime.now(timezone.utc))
        with self._lock:
            incident = TechnicalIncident(
                incident_id=(incident_id or f"incident-{uuid4().hex}").strip(),
                title=title.strip(),
                message=message.strip(),
                started_at=started_at,
            )
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
            resolved = TechnicalIncident(
                incident_id=current.incident_id,
                title=current.title,
                message=current.message,
                started_at=current.started_at,
                status=IncidentStatus.RESOLVED,
                resolved_at=_utc(now or datetime.now(timezone.utc)),
            )
            self._incidents[incident_id] = resolved
            if self._notification_center is not None:
                self._notification_center.publish(EcosystemNotification(
                    notification_id=f"incident-resolved-{uuid4().hex}",
                    kind=NotificationKind.RECOVERY,
                    severity=NotificationSeverity.IMPORTANT,
                    title="Problema técnico resolvido",
                    message=f"O incidente {incident_id} foi resolvido. O ecossistema só volta a operar se as demais barreiras de segurança também estiverem liberadas.",
                    requires_attention=True,
                ))
            return resolved

    def active(self) -> tuple[TechnicalIncident, ...]:
        with self._lock:
            return tuple(item for item in self._incidents.values() if item.status is IncidentStatus.ACTIVE)

    def execution_blocked(self) -> bool:
        return bool(self.active())

    def status(self) -> dict[str, object]:
        active = self.active()
        return {
            "status": "INCIDENT" if active else "HEALTHY",
            "execution_blocked": bool(active),
            "active_incidents": tuple(item.incident_id for item in active),
        }

    def _publish(self, incident: TechnicalIncident) -> None:
        if self._notification_center is None:
            return
        self._notification_center.publish(EcosystemNotification(
            notification_id=f"incident-open-{incident.incident_id}",
            kind=NotificationKind.RECOVERY,
            severity=NotificationSeverity.CRITICAL,
            title="Problema técnico detectado",
            message=f"{incident.message} Novas ordens estão bloqueadas enquanto o problema é investigado e resolvido.",
            requires_attention=True,
            blocking=True,
        ))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("incident timestamps must include timezone")
    return value.astimezone(timezone.utc)
