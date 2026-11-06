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
    """Classifies material events without deciding whether a trade is valid."""

    def __init__(self) -> None:
        self._notifications: list[EcosystemNotification] = []



    def restore(self, items: list[dict]) -> None:
        """Restore persisted notifications; invalid records are ignored safely."""
        restored: list[EcosystemNotification] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                notification_id = item["notification_id"]
                kind = item["kind"]
                severity = item["severity"]
                title = item["title"]
                message = item["message"]
                requires_attention = item.get("requires_attention", False)
                blocking = item.get("blocking", False)
                # Persisted JSON is untrusted input: do not coerce strings such
                # as "false" to True or arbitrary objects into display text.
                if not all(isinstance(value, str) for value in (
                    notification_id, kind, severity, title, message
                )):
                    continue
                if type(requires_attention) is not bool or type(blocking) is not bool:
                    continue
                if not notification_id.strip() or not title.strip() or not message.strip():
                    continue
                if len(notification_id) > 160 or len(title) > 240 or len(message) > 4000:
                    continue
                notification = EcosystemNotification(
                    notification_id=notification_id,
                    kind=NotificationKind(kind),
                    severity=NotificationSeverity(severity),
                    title=title,
                    message=message,
                    requires_attention=requires_attention,
                    blocking=blocking,
                )
                restored.append(notification)
            except (KeyError, TypeError, ValueError):
                continue
        self._notifications = restored

    def publish(self, notification: EcosystemNotification) -> EcosystemNotification:
        if not isinstance(notification, EcosystemNotification):
            raise ValueError("notification is required")
        if not notification.title.strip() or not notification.message.strip():
            raise ValueError("notification title and message are required")
        self._notifications.append(notification)
        return notification

    def publish_update(self, notification_id: str, title: str, message: str, *, important: bool = True, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> EcosystemNotification:
        severity = NotificationSeverity.IMPORTANT if important else NotificationSeverity.INFO
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SYSTEM_UPDATE, severity, title, message, requires_attention=important))

    def publish_ecosystem_update(self, notification_id: str, title: str, message: str) -> EcosystemNotification:
        return self.publish_update(notification_id, title, message, important=True, update_kind=UpdateKind.ECOSYSTEM)

    def publish_security_update(self, notification_id: str, title: str, message: str, *, blocking: bool = False) -> EcosystemNotification:
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SECURITY, NotificationSeverity.CRITICAL if blocking else NotificationSeverity.IMPORTANT, title, message, requires_attention=True, blocking=blocking))

    def visible(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        if include_info:
            return tuple(self._notifications)
        return tuple(n for n in self._notifications if n.severity is not NotificationSeverity.INFO)

    def critical(self) -> tuple[EcosystemNotification, ...]:
        return tuple(n for n in self._notifications if n.severity is NotificationSeverity.CRITICAL)

    def all(self) -> tuple[EcosystemNotification, ...]:
        return tuple(self._notifications)

    @staticmethod
    def summarize(events: Iterable[EcosystemNotification]) -> dict[str, int]:
        counts = {severity.value: 0 for severity in NotificationSeverity}
        for event in events:
            counts[event.severity.value] += 1
        return counts
