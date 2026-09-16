from core.ecosystem_notifications import (
    EcosystemNotification,
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


class MemoryStateStore:
    def __init__(self):
        self.values = {}

    def get(self, *, tenant_id, subject_id, namespace):
        return self.values.get((tenant_id, subject_id, namespace))

    def put(self, *, tenant_id, subject_id, namespace, payload):
        self.values[(tenant_id, subject_id, namespace)] = payload


def test_durable_publish_does_not_overwrite_event_from_another_center():
    store = MemoryStateStore()
    first = EcosystemNotificationCenter(state_store=store, require_durable=True)
    second = EcosystemNotificationCenter(state_store=store, require_durable=True)

    first.publish(EcosystemNotification("1", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "A", "first"))
    assert [item.notification_id for item in second.all()] == ["1"]
    first.publish(EcosystemNotification("2", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "B", "second"))
    second.publish(EcosystemNotification("3", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "C", "third"))

    assert [item.notification_id for item in second.all()] == ["1", "2", "3"]
