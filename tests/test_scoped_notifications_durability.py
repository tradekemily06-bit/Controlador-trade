from __future__ import annotations

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from security.http_identity import clear_trusted_identity, require_trusted_identity
from storage.scoped_state_store import SQLiteScopedStateStore


def _identity(tenant: str, subject: str):
    require_trusted_identity({
        "PATH_INFO": "/api/notifications",
        "controlador.trusted_tenant_id": tenant,
        "controlador.trusted_subject_id": subject,
        "controlador.trusted_role": "user",
    })


def test_notifications_survive_restart_and_do_not_cross_tenants(tmp_path):
    state = SQLiteScopedStateStore(tmp_path / "state.db")
    try:
        _identity("tenant-a", "user-a")
        first = EcosystemNotificationCenter(state_store=state, require_durable=True)
        first.publish(EcosystemNotification("a-1", NotificationKind.RISK, NotificationSeverity.IMPORTANT, "A", "private A"))

        _identity("tenant-b", "user-a")
        second = EcosystemNotificationCenter(state_store=state, require_durable=True)
        assert all(item.notification_id != "a-1" for item in second.all())

        _identity("tenant-a", "user-a")
        restarted = EcosystemNotificationCenter(state_store=state, require_durable=True)
        assert any(item.notification_id == "a-1" for item in restarted.all())
    finally:
        clear_trusted_identity()


def test_global_notifications_are_visible_without_cross_tenant_private_data(tmp_path):
    state = SQLiteScopedStateStore(tmp_path / "state.db")
    center = EcosystemNotificationCenter(state_store=state, require_durable=True)
    center.publish_global(EcosystemNotification("global-1", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.CRITICAL, "Update", "global"))

    try:
        _identity("tenant-a", "user-a")
        assert any(item.notification_id == "global-1" for item in EcosystemNotificationCenter(state_store=state, require_durable=True).all())
    finally:
        clear_trusted_identity()
