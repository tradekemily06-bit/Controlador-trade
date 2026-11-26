from core.ecosystem_notifications import (
    EcosystemNotification,
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


def test_notification_center_deduplicates_stable_notification_ids():
    center = EcosystemNotificationCenter()
    first = EcosystemNotification(
        notification_id="market:EURUSD:5m:2026-09-07T10:00:00+00:00:COMPRA",
        kind=NotificationKind.MARKET,
        severity=NotificationSeverity.IMPORTANT,
        title="Mudança de sinal",
        message="COMPRA",
    )
    duplicate = EcosystemNotification(
        notification_id=first.notification_id,
        kind=NotificationKind.MARKET,
        severity=NotificationSeverity.IMPORTANT,
        title="Mudança de sinal",
        message="COMPRA",
    )

    assert center.publish(first) == first
    assert center.publish(duplicate) == first
    assert len(center.all()) == 1
