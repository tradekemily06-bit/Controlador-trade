from security.http_identity import TrustedHttpIdentity, _current_identity

from core.ecosystem_notifications import (
    EcosystemNotification,
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


def test_important_and_critical_events_are_visible_without_ui_noise():
    token = _current_identity.set(TrustedHttpIdentity("user-test", "tenant-test", "user"))
    try:
        center = EcosystemNotificationCenter()
        center.publish(EcosystemNotification("1", NotificationKind.MARKET, NotificationSeverity.INFO, "Info", "minor"))
        center.publish(EcosystemNotification("2", NotificationKind.RISK, NotificationSeverity.IMPORTANT, "Risk", "attention", True))
        center.publish(EcosystemNotification("3", NotificationKind.SECURITY, NotificationSeverity.CRITICAL, "Security", "blocked", True, True))
        
        visible = center.visible()
        assert [item.notification_id for item in visible] == ["2", "3"]
        assert center.critical()[0].notification_id == "3"
    finally:
        _current_identity.reset(token)


def test_system_update_is_important_by_default():
    center = EcosystemNotificationCenter()
    item = center.publish_update("update-1", "Atualização", "Nova versão disponível.")

    assert item.kind is NotificationKind.SYSTEM_UPDATE
    assert item.severity is NotificationSeverity.IMPORTANT
    assert item.requires_attention is True
