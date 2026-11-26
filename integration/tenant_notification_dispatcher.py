from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.ecosystem_notifications import EcosystemNotification
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState


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

    def publish(self, context: TenantContext, notification: EcosystemNotification) -> bool:
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
        if not isinstance(notification, EcosystemNotification):
            raise TypeError("EcosystemNotification is required")
        if not notification.notification_id.strip() or not notification.title.strip() or not notification.message.strip():
            raise ValueError("notification id, title and message are required")
        payload: dict[str, Any] = asdict(notification)
        payload["kind"] = notification.kind.value
        payload["severity"] = notification.severity.value
        return self.state.append_notification(context, payload)
