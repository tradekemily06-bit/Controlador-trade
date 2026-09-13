from core.ecosystem_notifications import (
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


def test_ecosystem_update_is_material_and_visible():
    center = EcosystemNotificationCenter()
    event = center.publish_ecosystem_update(
        "update-1",
        "Atualização do ecossistema disponível",
        "Uma atualização importante precisa ser aplicada.",
    )
    assert event.kind is NotificationKind.SYSTEM_UPDATE
    assert event.severity is NotificationSeverity.IMPORTANT
    assert event in center.visible()


def test_blocking_security_update_is_critical():
    center = EcosystemNotificationCenter()
    event = center.publish_security_update(
        "security-1", "Atualização de segurança", "Correção crítica necessária.", blocking=True
    )
    assert event.severity is NotificationSeverity.CRITICAL
    assert event in center.critical()
