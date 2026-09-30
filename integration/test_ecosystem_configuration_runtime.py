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


def test_mt5_senior_context_uses_only_observed_risk_domains():
    from core.operational_state import OperationalState
    from data.models import Candle
    from datetime import datetime, timezone

    service = ConfiguredEcosystemService()
    candles = (Candle(datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 101, 99, 100, 10),)
    state = OperationalState(balance=1000, equity=1005, open_positions=1, net_position=0.01, exposure=100, trades_today=2, consecutive_losses=0)
    context = service._build_mt5_senior_context(candles, state)
    assert context.quality.value == "COMPLETE"
    assert context.execution_authorized is False
    assert context.risk_assessment.execution_authorized is False
    assert {item.domain.value for item in context.risk_assessment.observations} == {"CAPITAL", "POSITION", "DATA_QUALITY"}
