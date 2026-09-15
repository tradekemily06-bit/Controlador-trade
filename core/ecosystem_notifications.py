from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable
from uuid import uuid4


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
    NAMESPACE = "ecosystem.notifications.v1"
    GLOBAL_TENANT = "__system__"
    GLOBAL_SUBJECT = "__global__"
    DEFAULT_CACHE_SIZE = 256

    def __init__(self, *, state_store=None, require_durable: bool = False, cache_size: int = DEFAULT_CACHE_SIZE) -> None:
        if cache_size < 1:
            raise ValueError("cache_size must be greater than zero")
        self._global_notifications: list[EcosystemNotification] = []
        self._scoped_notifications: OrderedDict[tuple[str, str], list[EcosystemNotification]] = OrderedDict()
        self._cache_size = int(cache_size)
        self._state_store = state_store
        self._require_durable = bool(require_durable)
        self._global_loaded = False

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
        return (tenant_id, subject_id) if tenant_id and subject_id else None

    @staticmethod
    def _decode(payload: object) -> list[EcosystemNotification]:
        if not isinstance(payload, list):
            raise RuntimeError("notification state is corrupt")
        try:
            return [EcosystemNotification(notification_id=str(item["notification_id"]), kind=NotificationKind(str(item["kind"])), severity=NotificationSeverity(str(item["severity"])), title=str(item["title"]), message=str(item["message"]), requires_attention=bool(item.get("requires_attention", False)), blocking=bool(item.get("blocking", False))) for item in payload]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("notification state is corrupt") from exc

    def _load(self, scope: tuple[str, str]) -> list[EcosystemNotification]:
        if self._state_store is None:
            if self._require_durable:
                raise RuntimeError("durable notification state provider is required")
            return []
        payload = self._state_store.get(tenant_id=scope[0], subject_id=scope[1], namespace=self.NAMESPACE)
        return [] if payload is None else self._decode(payload)

    def _save(self, scope: tuple[str, str], events: list[EcosystemNotification]) -> None:
        if self._state_store is None:
            if self._require_durable:
                raise RuntimeError("durable notification state provider is required")
            return
        self._state_store.put(tenant_id=scope[0], subject_id=scope[1], namespace=self.NAMESPACE, payload=[asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in events])

    def _global(self) -> list[EcosystemNotification]:
        if not self._global_loaded:
            self._global_notifications = self._load((self.GLOBAL_TENANT, self.GLOBAL_SUBJECT))
            self._global_loaded = True
        return self._global_notifications

    def _scoped(self, scope: tuple[str, str]) -> list[EcosystemNotification]:
        cached = self._scoped_notifications.get(scope)
        if cached is not None:
            self._scoped_notifications.move_to_end(scope)
            return cached
        events = self._load(scope)
        self._scoped_notifications[scope] = events
        self._scoped_notifications.move_to_end(scope)
        while len(self._scoped_notifications) > self._cache_size:
            self._scoped_notifications.popitem(last=False)
        return events

    def _replace_cache(self, scope: tuple[str, str], events: list[EcosystemNotification]) -> None:
        if scope == (self.GLOBAL_TENANT, self.GLOBAL_SUBJECT):
            self._global_notifications = events
            self._global_loaded = True
            return
        self._scoped_notifications[scope] = events
        self._scoped_notifications.move_to_end(scope)
        while len(self._scoped_notifications) > self._cache_size:
            self._scoped_notifications.popitem(last=False)

    def _current(self) -> tuple[EcosystemNotification, ...]:
        scope = self._trusted_scope()
        scoped = tuple(self._scoped(scope)) if scope is not None else ()
        return tuple(self._global()) + scoped

    def publish(self, notification: EcosystemNotification) -> EcosystemNotification:
        if not isinstance(notification, EcosystemNotification):
            raise ValueError("notification is required")
        if not notification.notification_id.strip() or not notification.title.strip() or not notification.message.strip():
            raise ValueError("notification id, title and message are required")
        scope = self._trusted_scope() or (self.GLOBAL_TENANT, self.GLOBAL_SUBJECT)
        events = self._load(scope)
        events.append(notification)
        self._save(scope, events)
        self._replace_cache(scope, events)
        return notification

    def new_id(self, prefix: str = "event") -> str:
        return f"{prefix}-{uuid4().hex}"

    def publish_update(self, notification_id: str, title: str, message: str, *, important: bool = True, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> EcosystemNotification:
        severity = NotificationSeverity.IMPORTANT if important else NotificationSeverity.INFO
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SYSTEM_UPDATE, severity, title, message, requires_attention=important))

    def publish_ecosystem_update(self, notification_id: str, title: str, message: str) -> EcosystemNotification:
        return self.publish_update(notification_id, title, message, important=True, update_kind=UpdateKind.ECOSYSTEM)

    def publish_security_update(self, notification_id: str, title: str, message: str, *, blocking: bool = False) -> EcosystemNotification:
        return self.publish(EcosystemNotification(notification_id, NotificationKind.SECURITY, NotificationSeverity.CRITICAL if blocking else NotificationSeverity.IMPORTANT, title, message, requires_attention=True, blocking=blocking))

    def visible(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        events = self._current()
        return events if include_info else tuple(n for n in events if n.severity is not NotificationSeverity.INFO)

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
