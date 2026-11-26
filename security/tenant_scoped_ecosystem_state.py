from __future__ import annotations

from typing import Any

from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext


class TenantScopedEcosystemState:
    """Tenant-scoped preferences and notifications.

    This service is intentionally separate from the legacy single-runtime
    EcosystemStateStore. It never imports or migrates legacy global records:
    assigning those records to a tenant requires a verified ownership process.
    The caller must supply TenantContext created by trusted auth middleware.
    """

    _PREFERENCES_KEY = "ecosystem:preferences"
    _NOTIFICATIONS_KEY = "ecosystem:notifications"

    def __init__(self, storage: SQLiteTenantStorage) -> None:
        if not isinstance(storage, SQLiteTenantStorage):
            raise TypeError("SQLiteTenantStorage is required")
        self.storage = storage

    @staticmethod
    def _context(context: TenantContext | None) -> TenantContext:
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
        return context

    def load_preferences(self, context: TenantContext) -> dict[str, Any] | None:
        value = self.storage.get(self._context(context), self._PREFERENCES_KEY)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("stored tenant preferences have an invalid shape")
        return value

    def save_preferences(self, context: TenantContext, preferences: dict[str, Any]) -> None:
        if not isinstance(preferences, dict):
            raise ValueError("preferences must be an object")
        self.storage.put(self._context(context), self._PREFERENCES_KEY, preferences)

    def load_notifications(self, context: TenantContext) -> list[dict[str, Any]]:
        value = self.storage.get(self._context(context), self._NOTIFICATIONS_KEY)
        if value is None:
            return []
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError("stored tenant notifications have an invalid shape")
        return value

    def save_notifications(
        self, context: TenantContext, notifications: list[dict[str, Any]]
    ) -> None:
        if not isinstance(notifications, list) or any(
            not isinstance(item, dict) for item in notifications
        ):
            raise ValueError("notifications must be a list of objects")
        self.storage.put(self._context(context), self._NOTIFICATIONS_KEY, notifications)

    def append_notification(
        self, context: TenantContext, notification: dict[str, Any], *, limit: int = 500
    ) -> bool:
        """Append to one explicitly addressed tenant inbox; never broadcast."""
        trusted = self._context(context)
        if not isinstance(notification, dict):
            raise ValueError("notification must be an object")
        notification_id = notification.get("notification_id")
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise ValueError("notification_id is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise ValueError("limit must be an integer between 1 and 2000")
        items = self.load_notifications(trusted)
        if any(item.get("notification_id") == notification_id for item in items):
            return False
        items.append(dict(notification))
        self.save_notifications(trusted, items[-limit:])
        return True

    def readiness(self) -> dict[str, object]:
        return {
            "status": "LOCAL_TENANT_SCOPED_STORAGE",
            "tenant_context_required": True,
            "legacy_data_migrated": False,
            "production_durable": self.storage.ready_for_production,
            "production_ready": False,
            "execution_authorized": False,
        }
