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


def test_important_and_critical_events_are_visible_without_ui_noise():
    center = EcosystemNotificationCenter()
    center.publish(EcosystemNotification("1", NotificationKind.MARKET, NotificationSeverity.INFO, "Info", "minor"))
    center.publish(EcosystemNotification("2", NotificationKind.RISK, NotificationSeverity.IMPORTANT, "Risk", "attention", True))
    center.publish(EcosystemNotification("3", NotificationKind.SECURITY, NotificationSeverity.CRITICAL, "Security", "blocked", True, True))

    visible = center.visible()
    assert [item.notification_id for item in visible] == ["2", "3"]
    assert center.critical()[0].notification_id == "3"


def test_system_update_is_important_by_default():
    center = EcosystemNotificationCenter()
    item = center.publish_update("update-1", "Atualização", "Nova versão disponível.")

    assert item.kind is NotificationKind.SYSTEM_UPDATE
    assert item.severity is NotificationSeverity.IMPORTANT
    assert item.requires_attention is True


def test_durable_publish_does_not_overwrite_event_from_another_center():
    store = MemoryStateStore()
    first = EcosystemNotificationCenter(state_store=store, require_durable=True)
    second = EcosystemNotificationCenter(state_store=store, require_durable=True)

    first.publish(EcosystemNotification("1", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "A", "first"))
    # Prime the second center's old cache, then publish from the first center.
    assert [item.notification_id for item in second.all()] == ["1"]
    first.publish(EcosystemNotification("2", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "B", "second"))
    second.publish(EcosystemNotification("3", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "C", "third"))

    assert [item.notification_id for item in second.all()] == ["1", "2", "3"]
