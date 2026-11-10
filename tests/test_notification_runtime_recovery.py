from threading import RLock

from core.ecosystem_notifications import EcosystemNotificationCenter
from core.ecosystem_state_store import NotificationHistoryUnavailableError
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


class _StateStore:
    def __init__(self, items, load_error=None):
        self.items = items
        self.notifications_load_error = load_error
        self.marked_unavailable = []
        self.restored = []
        self.saved = []

    def save_notifications(self, items):
        self.saved.append(items)

    def restore_notifications_from_quarantine(self, archive_id, *, confirmed=False):
        self.restored.append((archive_id, confirmed))
        return {"archive_id": archive_id, "restored_count": len(self.items)}

    def load_notifications(self):
        return self.items

    def mark_notifications_unavailable(self, category):
        self.marked_unavailable.append(category)
        self.notifications_load_error = category


def _service_with_store(store):
    service = ConfiguredEcosystemService.__new__(ConfiguredEcosystemService)
    service.state_store = store
    service.notifications = EcosystemNotificationCenter()
    service._notification_history_lock = RLock()
    return service


def test_recovery_refreshes_live_notification_center_after_persistent_restore():
    items = [{
        "notification_id": "recovered-1",
        "kind": "SECURITY",
        "severity": "CRITICAL",
        "title": "Alerta recuperado",
        "message": "Histórico validado",
        "requires_attention": True,
        "blocking": True,
    }]
    store = _StateStore(items)
    service = _service_with_store(store)

    result = service.restore_notification_history("archive-1", confirmed=True)

    assert result["archive_id"] == "archive-1"
    assert store.restored == [("archive-1", True)]
    assert [item.notification_id for item in service.notifications.all()] == ["recovered-1"]
    assert service.notifications.all()[0].blocking is True
    assert store.marked_unavailable == []


def test_recovery_keeps_history_unavailable_when_reload_reports_storage_error():
    store = _StateStore([], load_error="read_failed")
    service = _service_with_store(store)
    existing = {
        "notification_id": "existing-1",
        "kind": "SECURITY",
        "severity": "CRITICAL",
        "title": "Alerta anterior",
        "message": "Não deve ser apagado por uma releitura com erro",
        "requires_attention": True,
        "blocking": True,
    }
    service.notifications.restore([existing])
    original_center = service.notifications

    try:
        service.restore_notification_history("archive-1", confirmed=True)
    except NotificationHistoryUnavailableError:
        pass
    else:
        raise AssertionError("restoration must fail closed when reload reports an error")

    assert store.marked_unavailable == ["read_failed"]

    assert service.notifications is original_center
    assert [item.notification_id for item in service.notifications.all()] == ["existing-1"]


def test_publish_uses_unique_id_after_recovered_history():
    items = [{"notification_id": "event-2", "kind": "SECURITY", "severity": "CRITICAL", "title": "Recuperado", "message": "Histórico", "requires_attention": True, "blocking": True}]
    store = _StateStore(items)
    service = _service_with_store(store)
    service.notifications.restore(items)
    published = service.publish_material_event("RISK", "Novo", "Após recuperação", critical=True)
    assert published["notification_id"] != "event-2"
    assert published["notification_id"].startswith("event-")
    assert len({item["notification_id"] for item in store.saved[-1]}) == 2


def test_restore_marks_duplicate_notification_ids_as_invalid():
    duplicate = {"notification_id": "same-id", "kind": "SECURITY", "severity": "CRITICAL", "title": "Alerta", "message": "Registro", "requires_attention": True, "blocking": True}
    center = EcosystemNotificationCenter()

    center.restore([duplicate, dict(duplicate)])

    assert center.restore_had_invalid_records is True
    assert len(center.all()) == 1
