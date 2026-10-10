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


def test_mt5_analysis_does_not_treat_required_candle_and_filters_as_passed_without_evidence():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import Mock

    service = ConfiguredEcosystemService()
    service.execution_provider = "ic_markets_mt5_demo"
    service.operational_runtime = object()
    service.trading_runtime = SimpleNamespace(
        orchestrator=Mock(),
        market_data_state=None,
    )
    service.mt5_operational_adapter = SimpleNamespace(read_operational_state=lambda: None)
    service._record_analysis = lambda _record: None
    service.trading_runtime.orchestrator.evaluate.return_value = SimpleNamespace(
        analysis=object(),
        market_data=SimpleNamespace(candles=(), source="test"),
        timestamp=datetime.now(timezone.utc),
    )

    service.analyze_mt5_market(symbol="EURUSD", timeframe="5m", limit=100)

    kwargs = service.trading_runtime.orchestrator.evaluate.call_args.kwargs
    assert kwargs["confirmed"] is False
    assert kwargs["filters_ok"] is False


def test_mt5_analysis_accepts_explicit_confirmation_and_filter_evidence():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import Mock

    service = ConfiguredEcosystemService()
    service.execution_provider = "ic_markets_mt5_demo"
    service.operational_runtime = object()
    service.trading_runtime = SimpleNamespace(
        orchestrator=Mock(),
        market_data_state=None,
    )
    service.mt5_operational_adapter = SimpleNamespace(read_operational_state=lambda: None)
    service._record_analysis = lambda _record: None
    service.trading_runtime.orchestrator.evaluate.return_value = SimpleNamespace(
        analysis=object(),
        market_data=SimpleNamespace(candles=(), source="test"),
        timestamp=datetime.now(timezone.utc),
    )

    service.analyze_mt5_market(
        symbol="EURUSD", timeframe="5m", limit=100, confirmed=True, filters_ok=True
    )

    kwargs = service.trading_runtime.orchestrator.evaluate.call_args.kwargs
    assert kwargs["confirmed"] is True
    assert kwargs["filters_ok"] is True
