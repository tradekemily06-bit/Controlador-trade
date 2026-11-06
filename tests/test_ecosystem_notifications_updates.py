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


def test_configured_service_surfaces_audit_persistence_failure_as_critical(monkeypatch):
    from types import SimpleNamespace

    import integration.ecosystem_service as base_service
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setattr(
        base_service,
        "AUDIT",
        SimpleNamespace(persistence_available=False, persistence_error="write_failed"),
    )
    service = ConfiguredEcosystemService()

    items = service._operational_notifications()
    audit_items = [item for item in items if item["title"] == "SECURITY_AUDIT_PERSISTENCE_FAILED"]

    assert len(audit_items) == 1
    assert audit_items[0]["kind"] == "SECURITY"
    assert audit_items[0]["severity"] == "CRITICAL"
    assert audit_items[0]["requires_attention"] is True
    assert audit_items[0]["blocking"] is True


def test_configured_service_does_not_report_unconfigured_audit_as_failure(monkeypatch):
    from types import SimpleNamespace

    import integration.ecosystem_service as base_service
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setattr(
        base_service,
        "AUDIT",
        SimpleNamespace(persistence_available=False, persistence_error=None),
    )
    service = ConfiguredEcosystemService()

    assert not any(
        item["title"] == "SECURITY_AUDIT_PERSISTENCE_FAILED"
        for item in service._operational_notifications()
    )
