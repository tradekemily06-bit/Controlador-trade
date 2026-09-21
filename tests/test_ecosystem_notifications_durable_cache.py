from core.ecosystem_notifications import (
    EcosystemNotification,
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)
from security.http_identity import clear_trusted_identity, require_trusted_identity


class MemoryStateStore:
    def __init__(self):
        self.values = {}

    def get(self, *, tenant_id, subject_id, namespace):
        return self.values.get((tenant_id, subject_id, namespace))

    def put(self, *, tenant_id, subject_id, namespace, payload):
        self.values[(tenant_id, subject_id, namespace)] = payload

    def update(self, *, tenant_id, subject_id, namespace, updater):
        key = (tenant_id, subject_id, namespace)
        value = updater(self.values.get(key))
        self.values[key] = value
        return value


def _identity():
    require_trusted_identity({
        "PATH_INFO": "/api/notifications",
        "controlador.trusted_tenant_id": "tenant-a",
        "controlador.trusted_subject_id": "user-a",
        "controlador.trusted_role": "user",
    })


def test_durable_publish_does_not_overwrite_event_from_another_center():
    store = MemoryStateStore()
    try:
        _identity()
        first = EcosystemNotificationCenter(state_store=store, require_durable=True)
        second = EcosystemNotificationCenter(state_store=store, require_durable=True)

        first.publish(EcosystemNotification("1", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "A", "first"))
        assert [item.notification_id for item in second.all()] == ["1"]
        first.publish(EcosystemNotification("2", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "B", "second"))
        second.publish(EcosystemNotification("3", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "C", "third"))

        assert [item.notification_id for item in second.all()] == ["1", "2", "3"]
    finally:
        clear_trusted_identity()
