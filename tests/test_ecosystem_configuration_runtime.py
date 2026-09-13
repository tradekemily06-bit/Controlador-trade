from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def test_notification_preferences_filter_important_events_but_not_critical():
    service = ConfiguredEcosystemService()
    service.publish_material_event("RISK", "Risco", "Limite preventivo atingido.")
    service.publish_material_event("SECURITY", "Segurança", "Bloqueio crítico.", critical=True, blocking=True)

    service.update_notification_preferences({"risk_enabled": False})
    summary = service.notification_summary()

    assert summary["count"] == 1
    assert summary["critical_count"] == 1
    assert summary["items"][0]["severity"] == "CRITICAL"
    assert summary["items"][0]["kind"] == "SECURITY"


def test_system_updates_follow_their_preference():
    service = ConfiguredEcosystemService()
    service.publish_ecosystem_update("Atualização", "Atualização importante.")

    assert service.notification_summary()["count"] == 1
    service.update_notification_preferences({"system_updates_enabled": False})
    assert service.notification_summary()["count"] == 0
    assert len(service.all_notifications()) == 1
