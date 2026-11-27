from core.ecosystem_notifications import (
    EcosystemNotification,
    NotificationKind,
    NotificationSeverity,
)
from core.ecosystem_state_store import EcosystemStateStore
from core.notification_outbox import PersistentNotificationOutbox
from integration.ecosystem_service import EcosystemService


def test_published_notification_is_persisted_and_queued_for_external_delivery(tmp_path):
    state_store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite3")
    outbox = PersistentNotificationOutbox(tmp_path / "notification-outbox.sqlite3")
    service = EcosystemService(
        notification_state_store=state_store,
        notification_outbox=outbox,
    )
    notification = EcosystemNotification(
        notification_id="system-update-001",
        kind=NotificationKind.SYSTEM_UPDATE,
        severity=NotificationSeverity.IMPORTANT,
        title="Atualização do sistema",
        message="Uma nova versão foi preparada.",
        requires_attention=True,
    )

    published = service.publish_notification(notification)

    assert published == notification
    assert state_store.load_notifications()[0]["notification_id"] == "system-update-001"
    assert outbox.status_counts()["PENDING"] == 1
    assert service.notification_summary()["external_delivery"] == "OUTBOX_ONLY_NO_PROVIDER"


def test_duplicate_notification_id_does_not_duplicate_external_delivery(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "notification-outbox.sqlite3")
    service = EcosystemService(notification_outbox=outbox)
    notification = EcosystemNotification(
        notification_id="same-event",
        kind=NotificationKind.MARKET,
        severity=NotificationSeverity.IMPORTANT,
        title="Alerta de mercado",
        message="Contexto mudou.",
    )

    service.publish_notification(notification)
    service.publish_notification(notification)

    assert outbox.status_counts()["PENDING"] == 1
