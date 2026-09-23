from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def test_configured_service_exposes_safe_preferences_and_notification_summary():
    service = ConfiguredEcosystemService()
    preferences = service.get_preferences()
    assert preferences["default_symbol"] == "EURUSD"
    assert preferences["candle"]["style"] == "CANDLESTICK"
    assert preferences["autonomous_operation_enabled"] is False
    assert preferences["real_execution_enabled"] is False
    assert service.notification_summary()["count"] == 0


def test_candle_preferences_are_updated_through_service_boundary():
    service = ConfiguredEcosystemService()
    updated = service.update_candle_preferences({"style": "HOLLOW", "color_mode": "CUSTOM", "bullish_color": "#00ff00"})
    assert updated["candle"]["style"] == "HOLLOW"
    assert updated["candle"]["color_mode"] == "CUSTOM"
    assert updated["candle"]["bullish_color"] == "#00ff00"


def test_ecosystem_update_surfaces_as_important_notification():
    service = ConfiguredEcosystemService()
    item = service.publish_ecosystem_update("Atualização disponível", "Uma atualização do ecossistema requer atenção.")
    summary = service.notification_summary()
    assert item["kind"] == "SYSTEM_UPDATE"
    assert item["severity"] == "IMPORTANT"
    assert summary["count"] == 1


def test_preferences_cannot_enable_real_or_autonomy():
    service = ConfiguredEcosystemService()
    try:
        service.update_preferences({"real_execution_enabled": True})
    except ValueError:
        pass
    else:
        raise AssertionError("REAL execution must remain outside preferences")

    try:
        service.update_preferences({"autonomous_operation_enabled": True})
    except ValueError:
        pass
    else:
        raise AssertionError("autonomy must remain outside preferences")


def test_use_mode_and_safe_preferences_persist_without_granting_authority(tmp_path):
    from core.ecosystem_preferences import EcosystemPreferencesStore, EcosystemUseMode
    db = tmp_path / "preferences.sqlite3"
    first = EcosystemPreferencesStore(database_path=str(db))
    first.update(use_mode=EcosystemUseMode.STUDY, trader_psychology_enabled=False)
    second = EcosystemPreferencesStore(database_path=str(db))
    assert second.preferences.use_mode is EcosystemUseMode.STUDY
    assert second.preferences.trader_psychology_enabled is False
    assert second.preferences.real_execution_enabled is False
    assert second.preferences.autonomous_operation_enabled is False
