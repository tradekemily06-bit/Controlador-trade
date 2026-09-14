"""Prioritized notifications for material ecosystem events.

All material events can be recorded; only important/critical events surface by
default so the operational screen stays clean. Notifications never decide or
authorize trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


class NotificationKind(str, Enum):
    SYSTEM_UPDATE = "SYSTEM_UPDATE"
    SECURITY = "SECURITY"
    MARKET = "MARKET"
    RISK = "RISK"
    CONNECTION = "CONNECTION"
    EXECUTION = "EXECUTION"
    LEARNING = "LEARNING"
    RECOVERY = "RECOVERY"


class UpdateKind(str, Enum):
    ECOSYSTEM = "ECOSYSTEM"
    SECURITY = "SECURITY"
    KNOWLEDGE = "KNOWLEDGE"
    DATA = "DATA"
    INTEGRATION = "INTEGRATION"


@dataclass(frozen=True)
class EcosystemNotification:
    notification_id: str
    kind: NotificationKind
    severity: NotificationSeverity
    title: str
    message: str
    requires_attention: bool = False
    blocking: bool = False


class EcosystemNotificationCenter:
    """Notification state isolated by trusted tenant+subject scope.

    Events emitted without a trusted identity are treated as global system
    events. Events emitted inside a trusted user request are private to that
    tenant+subject, while reads expose both global and the current user's events.
    """

    def __init__(self) -> None:
        self._global_notifications: list[EcosystemNotification] = []
        self._scoped_notifications: dict[tuple[str, str], list[EcosystemNotification]] = {}

    @staticmethod
    def _trusted_scope() -> tuple[str, str] | None:
        try:
            from security.http_identity import current_trusted_identity
            identity = current_trusted_identity()
        except Exception:
            identity = None
        if identity is None:
            return None
        tenant_id = str(identity.tenant_id).strip()
        subject_id = str(identity.subject_id).strip()
        if not tenant_id or not subject_id:
            return None
        return tenant_id, subject_id

    def _current(self) -> tuple[EcosystemNotification, ...]:
        scope = self._trusted_scope()
        scoped = tuple(self._scoped_notifications.get(scope, ())) if scope is not None else ()
        return tuple(self._global_notifications) + scoped

    def publish(self, notification: EcosystemNotification) -> EcosystemNotification:
        if not isinstance(notification, EcosystemNotification):
            raise ValueError("notification is required")
        if not notification.title.strip() or not notification.message.strip():
            raise ValueError("notification title and message are required")
        scope = self._trusted_scope()
        if scope is None:
            self._global_notifications.append(notification)
        else:
            self._scoped_notifications.setdefault(scope, []).append(notification)
        return notification

    def publish_update(self, notification_id: str, title: str, message: str, *, important: bool = True, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> EcosystemNotification:
        severity = NotificationSeverity.IMPORTANT if important else NotificationSeverity.INFO
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SYSTEM_UPDATE, severity, title, message, requires_attention=important))

    def publish_ecosystem_update(self, notification_id: str, title: str, message: str) -> EcosystemNotification:
        return self.publish_update(notification_id, title, message, important=True, update_kind=UpdateKind.ECOSYSTEM)

    def publish_security_update(self, notification_id: str, title: str, message: str, *, blocking: bool = False) -> EcosystemNotification:
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SECURITY, NotificationSeverity.CRITICAL if blocking else NotificationSeverity.IMPORTANT, title, message, requires_attention=True, blocking=blocking))

    def visible(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        events = self._current()
        if include_info:
            return events
        return tuple(n for n in events if n.severity is not NotificationSeverity.INFO)

    def critical(self) -> tuple[EcosystemNotification, ...]:
        return tuple(n for n in self._current() if n.severity is NotificationSeverity.CRITICAL)

    def all(self) -> tuple[EcosystemNotification, ...]:
        return self._current()

    @staticmethod
    def summarize(events: Iterable[EcosystemNotification]) -> dict[str, int]:
        counts = {severity.value: 0 for severity in NotificationSeverity}
        for event in events:
            counts[event.severity.value] += 1
        return counts
