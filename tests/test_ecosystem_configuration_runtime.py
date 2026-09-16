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


def test_psychology_check_in_is_disabled_at_runtime_when_preference_is_off():
    service = ConfiguredEcosystemService()
    enabled = service.psychology_check_in({
        "emotional_state": "ansiedade",
        "urge_to_trade": 9,
        "recent_losses": 2,
        "fatigue": 2,
        "confidence": 5,
        "rule_adherence": 5,
    })
    assert enabled["enabled"] is True
    assert enabled["trading_authorized"] is False


def test_configured_service_binds_operational_risk_to_authoritative_runtime():
    service = ConfiguredEcosystemService()

    assert service.operational_runtime is not None
    bridge = service.operational_risk_bridge

    assert bridge._runtime_barrier_bound is True
    assert bridge.operational_barrier_provider is not None
    assert bridge.operational_state_provider is service.operational_runtime.risk_state_provider
