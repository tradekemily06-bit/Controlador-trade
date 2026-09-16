from security.http_identity import TrustedHttpIdentity, _current_identity

from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def test_notification_preferences_filter_important_events_but_not_critical():
    token = _current_identity.set(TrustedHttpIdentity("user-test", "tenant-test", "user"))
    try:
        service = ConfiguredEcosystemService()
        service.publish_material_event("RISK", "Risco", "Limite preventivo atingido.")
        service.publish_material_event("SECURITY", "Segurança", "Bloqueio crítico.", critical=True, blocking=True)
        service.update_notification_preferences({"risk_enabled": False})
        summary = service.notification_summary()
        assert summary["count"] == 1
        assert summary["critical_count"] == 1
        assert summary["items"][0]["severity"] == "CRITICAL"
        assert summary["items"][0]["kind"] == "SECURITY"
    finally:
        _current_identity.reset(token)


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

    service.update_preferences({"psychology_enabled": False})
    disabled = service.psychology_check_in({
        "emotional_state": "ansiedade",
        "urge_to_trade": 9,
        "recent_losses": 2,
        "fatigue": 2,
        "confidence": 5,
        "rule_adherence": 5,
    })
    assert disabled["enabled"] is False
    assert disabled["risk_level"] == "DISABLED"
    assert disabled["flags"] == []
    assert disabled["trading_authorized"] is False


def test_advanced_psychology_is_disabled_without_affecting_execution_safety_contract():
    service = ConfiguredEcosystemService()
    service.update_preferences({"psychology_enabled": False})
    result = service.advanced_psychology_assessment({"operations": 10, "losses": 8, "urgency": 10})

    assert result["enabled"] is False
    assert result["patterns"] == []
    assert result["trading_authorized"] is False
