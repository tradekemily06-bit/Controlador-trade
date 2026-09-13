"""Prioritized notifications for material ecosystem events.

The center separates important events from technical noise so the main UI can
stay clean while critical information remains visible and auditable.
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

    def publish(self, notification: EcosystemNotification) -> EcosystemNotification:
        if not isinstance(notification, EcosystemNotification):
            raise ValueError("notification is required")
        if not notification.title.strip() or not notification.message.strip():
            raise ValueError("notification title and message are required")
        self._notifications.append(notification)
        return notification

    def publish_update(self, notification_id: str, title: str, message: str, *, important: bool = True) -> EcosystemNotification:
        return self.publish(EcosystemNotification(
            notification_id=notification_id,
            kind=NotificationKind.SYSTEM_UPDATE,
            severity=NotificationSeverity.IMPORTANT if important else NotificationSeverity.INFO,
            title=title,
            message=message,
            requires_attention=important,
        ))

    def visible(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        """Return notifications suitable for the clean main UI."""
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
