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


def test_scoped_notifications_survive_restart_and_do_not_cross_tenants(tmp_path):
    state = SQLiteScopedStateStore(tmp_path / "state.db")
    try:
        _identity("tenant-a", "user-a")
        first = EcosystemNotificationCenter(state_store=state, require_durable=True)
        first.publish(EcosystemNotification("a1", NotificationKind.RISK, NotificationSeverity.CRITICAL, "Risk", "stop"))

        _identity("tenant-b", "user-a")
        assert [item.notification_id for item in EcosystemNotificationCenter(state_store=state, require_durable=True).all()] == []

        _identity("tenant-a", "user-a")
        restarted = EcosystemNotificationCenter(state_store=state, require_durable=True)
        assert [item.notification_id for item in restarted.all()] == ["a1"]
    finally:
        clear_trusted_identity()


def test_global_system_notification_is_visible_without_becoming_private_state(tmp_path):
    state = SQLiteScopedStateStore(tmp_path / "state.db")
    try:
        clear_trusted_identity()
        center = EcosystemNotificationCenter(state_store=state, require_durable=True)
        center.publish(EcosystemNotification("g1", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "Update", "system"))

        _identity("tenant-a", "user-a")
        assert [item.notification_id for item in EcosystemNotificationCenter(state_store=state, require_durable=True).all()] == ["g1"]
    finally:
        clear_trusted_identity()
