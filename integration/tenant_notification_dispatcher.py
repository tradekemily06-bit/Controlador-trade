from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState
from core.tenant_notification_outbox import TenantNotificationOutbox


class TenantNotificationDispatcher:
    """Persist an event only for an explicitly supplied trusted recipient.

    This dispatcher deliberately has no tenant enumeration or broadcast API.
    Market-wide fan-out must be implemented separately through explicit,
    consented subscriptions; private events must always name their recipient.
    """

    def __init__(self, state: TenantScopedEcosystemState) -> None:
        if not isinstance(state, TenantScopedEcosystemState):
            raise TypeError("TenantScopedEcosystemState is required")
        self.state = state
        self.outbox = TenantNotificationOutbox(state.storage)

    def publish(self, context: TenantContext, notification: EcosystemNotification) -> bool:
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
        if not isinstance(notification, EcosystemNotification):
            raise TypeError("EcosystemNotification is required")
        if (
            not isinstance(notification.notification_id, str)
            or not notification.notification_id.strip()
            or not isinstance(notification.title, str)
            or not notification.title.strip()
            or not isinstance(notification.message, str)
            or not notification.message.strip()
        ):
            raise ValueError("notification id, title and message are required")
        if not isinstance(notification.kind, NotificationKind):
            raise ValueError("notification kind must be a supported NotificationKind")
        if not isinstance(notification.severity, NotificationSeverity):
            raise ValueError("notification severity must be a supported NotificationSeverity")
        if not isinstance(notification.requires_attention, bool) or not isinstance(notification.blocking, bool):
            raise ValueError("notification flags must be boolean")
        payload: dict[str, Any] = asdict(notification)
        payload["kind"] = notification.kind.value
        payload["severity"] = notification.severity.value
        return self.outbox.publish(context, payload)
