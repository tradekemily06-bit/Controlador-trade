from core.ecosystem_notifications import (
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


def test_notifications_persist_and_restore_across_restart(tmp_path):
    path = str(tmp_path / "notifications.sqlite3")
    first = EcosystemNotificationCenter(database_path=path)
    first.publish(
        __import__("core.ecosystem_notifications", fromlist=["EcosystemNotification"]).EcosystemNotification(
            "n1",
            NotificationKind.RECOVERY,
            NotificationSeverity.CRITICAL,
            "Recuperação",
            "Reconciliação necessária",
            True,
            True,
        )
    )

    second = EcosystemNotificationCenter(database_path=path)
    items = second.all()
    assert len(items) == 1
    assert items[0].notification_id == "n1"
    assert items[0].severity is NotificationSeverity.CRITICAL
    assert items[0].blocking is True
