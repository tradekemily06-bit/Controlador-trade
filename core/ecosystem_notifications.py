"""Prioritized notifications for material ecosystem events.

All material events can be recorded; only important/critical events surface by
default so the operational screen stays clean. Notifications never decide or
authorize trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sqlite3
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

    def __init__(self, *, database_path: str | None = None) -> None:
        self.database_path = database_path
        self._notifications: list[EcosystemNotification] = self._load() if database_path else []

    def publish(self, notification: EcosystemNotification) -> EcosystemNotification:
        if not isinstance(notification, EcosystemNotification):
            raise ValueError("notification is required")
        if not notification.title.strip() or not notification.message.strip():
            raise ValueError("notification title and message are required")
        self._notifications.append(notification)
        self._save(notification)
        return notification

    def publish_update(self, notification_id: str, title: str, message: str, *, important: bool = True, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> EcosystemNotification:
        severity = NotificationSeverity.IMPORTANT if important else NotificationSeverity.INFO
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SYSTEM_UPDATE, severity, title, message, requires_attention=important))

    def publish_ecosystem_update(self, notification_id: str, title: str, message: str) -> EcosystemNotification:
        return self.publish_update(notification_id, title, message, important=True, update_kind=UpdateKind.ECOSYSTEM)

    def publish_security_update(self, notification_id: str, title: str, message: str, *, blocking: bool = False) -> EcosystemNotification:
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SECURITY, NotificationSeverity.CRITICAL if blocking else NotificationSeverity.IMPORTANT, title, message, requires_attention=True, blocking=blocking))

    def _load(self) -> list[EcosystemNotification]:
        try:
            path = Path(self.database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.database_path, timeout=5) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS notifications "
                    "(notification_id TEXT PRIMARY KEY, kind TEXT NOT NULL, severity TEXT NOT NULL, "
                    "title TEXT NOT NULL, message TEXT NOT NULL, requires_attention INTEGER NOT NULL, "
                    "blocking INTEGER NOT NULL)"
                )
                rows = db.execute(
                    "SELECT notification_id, kind, severity, title, message, requires_attention, blocking "
                    "FROM notifications ORDER BY rowid"
                ).fetchall()
            return [
                EcosystemNotification(
                    notification_id=row[0],
                    kind=NotificationKind(row[1]),
                    severity=NotificationSeverity(row[2]),
                    title=row[3],
                    message=row[4],
                    requires_attention=bool(row[5]),
                    blocking=bool(row[6]),
                )
                for row in rows
            ]
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return []

    def _save(self, notification: EcosystemNotification) -> None:
        if not self.database_path:
            return
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path, timeout=5) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS notifications "
                "(notification_id TEXT PRIMARY KEY, kind TEXT NOT NULL, severity TEXT NOT NULL, "
                "title TEXT NOT NULL, message TEXT NOT NULL, requires_attention INTEGER NOT NULL, "
                "blocking INTEGER NOT NULL)"
            )
            db.execute(
                "INSERT INTO notifications(notification_id, kind, severity, title, message, requires_attention, blocking) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    notification.notification_id,
                    notification.kind.value,
                    notification.severity.value,
                    notification.title,
                    notification.message,
                    int(notification.requires_attention),
                    int(notification.blocking),
                ),
            )

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
