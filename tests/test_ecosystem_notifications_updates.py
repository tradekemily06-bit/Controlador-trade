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

    import integration.ecosystem_configuration_runtime as configured_service
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setattr(
        configured_service,
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

    summary = service.notification_summary()
    assert summary["critical_count"] == 1
    assert any(
        item["title"] == "SECURITY_AUDIT_PERSISTENCE_FAILED"
        for item in summary["items"]
    )


def test_configured_service_does_not_report_unconfigured_audit_as_failure(monkeypatch):
    from types import SimpleNamespace

    import integration.ecosystem_configuration_runtime as configured_service
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    monkeypatch.setattr(
        configured_service,
        "AUDIT",
        SimpleNamespace(persistence_available=False, persistence_error=None),
    )
    service = ConfiguredEcosystemService()

    assert not any(
        item["title"] == "SECURITY_AUDIT_PERSISTENCE_FAILED"
        for item in service._operational_notifications()
    )



def test_notification_preferences_never_hide_critical_security_events():
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
    from core.ecosystem_notifications import EcosystemNotification

    service = ConfiguredEcosystemService()
    service.update_notification_preferences({
        "important_enabled": False,
        "security_enabled": False,
        "info_enabled": False,
    })
    critical = EcosystemNotification(
        "critical-security",
        NotificationKind.SECURITY,
        NotificationSeverity.CRITICAL,
        "Falha crítica",
        "A persistência da auditoria falhou.",
        requires_attention=True,
        blocking=True,
    )
    important = EcosystemNotification(
        "important-security",
        NotificationKind.SECURITY,
        NotificationSeverity.IMPORTANT,
        "Aviso de segurança",
        "Atualização disponível.",
        requires_attention=True,
    )
    service.notifications.publish(critical)
    service.notifications.publish(important)

    visible = service._visible_notifications(include_info=True)

    assert critical in visible
    assert important not in visible
    assert service.preferences.preferences.notifications.critical_enabled is True


def test_notification_center_restores_persisted_events_after_restart(tmp_path):
    from dataclasses import asdict

    from core.ecosystem_notifications import EcosystemNotification
    from core.ecosystem_state_store import EcosystemStateStore

    store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite")
    original = EcosystemNotificationCenter()
    event = EcosystemNotification(
        "persisted-1",
        NotificationKind.SECURITY,
        NotificationSeverity.CRITICAL,
        "Auditoria indisponível",
        "A trilha de auditoria não confirmou persistência.",
        requires_attention=True,
        blocking=True,
    )
    original.publish(event)
    store.save_notifications([
        asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
        for item in original.all()
    ])

    restored = EcosystemNotificationCenter()
    restored.restore(store.load_notifications())

    assert restored.all() == (event,)
    assert restored.critical() == (event,)



def test_notification_restore_rejects_coercible_or_oversized_untrusted_records():
    center = EcosystemNotificationCenter()
    center.restore([
        {
            "notification_id": "valid",
            "kind": "SECURITY",
            "severity": "CRITICAL",
            "title": "Falha crítica",
            "message": "Persistência indisponível.",
            "requires_attention": True,
            "blocking": True,
        },
        {
            "notification_id": "string-bool",
            "kind": "SECURITY",
            "severity": "CRITICAL",
            "title": "Registro adulterado",
            "message": "Não deve converter texto em booleano.",
            "requires_attention": "false",
            "blocking": "false",
        },
        {
            "notification_id": "oversized",
            "kind": "SECURITY",
            "severity": "CRITICAL",
            "title": "x" * 241,
            "message": "Mensagem.",
        },
        None,
        "not-a-record",
    ])

    restored = center.all()
    assert len(restored) == 1
    assert restored[0].notification_id == "valid"
    assert restored[0].blocking is True


def test_configured_service_persists_notifications_across_service_restart(monkeypatch, tmp_path):
    import integration.ecosystem_configuration_runtime as configured_service
    from core.ecosystem_state_store import EcosystemStateStore as RealStateStore
    from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService

    database = tmp_path / "ecosystem-state.sqlite"
    monkeypatch.setattr(
        configured_service,
        "EcosystemStateStore",
        lambda _path: RealStateStore(database),
    )

    first = ConfiguredEcosystemService()
    published = first.publish_material_event(
        "SECURITY",
        "Auditoria persistente",
        "Evento crítico preservado entre reinicializações.",
        critical=True,
        blocking=True,
    )

    restarted = ConfiguredEcosystemService()
    restored = restarted.all_notifications()

    assert any(
        item["notification_id"] == published["notification_id"]
        and item["severity"] == "CRITICAL"
        and item["blocking"] is True
        for item in restored
    )
