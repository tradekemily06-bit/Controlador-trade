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
    candles = tuple(Candle(datetime(2026, 1, 1, minute=i, tzinfo=timezone.utc), 100 + i, 101 + i, 99 + i, 100 + i, 10 + i) for i in range(3))
    state = OperationalState(balance=1000, equity=1005, open_positions=1, net_position=0.01, exposure=100, trades_today=2, consecutive_losses=0)
    context = service._build_mt5_senior_context(candles, state)
    assert context.quality.value == "COMPLETE"
    assert context.execution_authorized is False
    assert context.risk_assessment.execution_authorized is False
    assert {item.domain.value for item in context.risk_assessment.observations} == {"CAPITAL", "POSITION", "DATA_QUALITY"}


def test_mt5_cycle_wires_controlled_automation_into_canonical_runtime():
    from core.operational_state import OperationalState
    from execution.gateway import GatewayResult, GatewayStatus

    class FakeRuntime:
        def __init__(self):
            self.kwargs = None
        def run(self, *args, **kwargs):
            self.kwargs = kwargs
            return "runtime-result"

    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    fake = FakeRuntime()
    from types import SimpleNamespace
    service.operational_runtime = SimpleNamespace(checkpoint_store=object())
    service.trading_runtime = fake
    service.mt5_operational_adapter.read_operational_state = lambda: OperationalState(
        realized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
        balance=1000.0,
        equity=1000.0,
        open_positions=0,
        net_position=0.0,
        exposure=0.0,
    )

    result = service.run_mt5_cycle(symbol="EURUSD", timeframe="5m", limit=3)
    assert result == "runtime-result"
    assert fake.kwargs["automation_policy"].enabled is True
    assert callable(fake.kwargs["automation_readiness_factory"])
    assert callable(fake.kwargs["automation_risk_budget_factory"])


def test_mt5_cycle_blocks_when_selected_provider_is_not_mt5(tmp_path):
    from core.operational_runtime import build_operational_runtime
    service = ConfiguredEcosystemService(
        operational_runtime=build_operational_runtime(tmp_path),
        execution_provider="paper",
    )
    try:
        service.run_mt5_cycle(symbol="EURUSD")
    except RuntimeError as exc:
        assert "ic_markets_mt5_demo" in str(exc)
    else:
        raise AssertionError("MT5 cycle must not mix live MT5 state with a non-MT5 execution provider")


def test_mt5_runtime_uses_the_single_controlled_automation_service(tmp_path):
    from core.operational_runtime import build_operational_runtime
    service = ConfiguredEcosystemService(operational_runtime=build_operational_runtime(tmp_path))
    assert service.trading_runtime is not None
    assert service.trading_runtime.automation_service is service.automation


def test_operational_incident_is_exposed_through_notification_channel():
    from core.operational_runtime import build_operational_runtime
    service = ConfiguredEcosystemService(operational_runtime=build_operational_runtime(__import__("pathlib").Path("/tmp/controlador-notification-test")))
    service.operational_observability = lambda: {
        "execution": {"state": "BLOCKED"},
        "recovery": {"state": "SAFE_TO_RESUME"},
        "reconciliation": {"pending_request_ids": [], "unknown_request_ids": []},
        "kill_switch": {"enabled": False},
        "runtime_health": {"state": "OK"},
        "market_data": {"health": "HEALTHY"},
    }

    summary = service.notification_summary()

    assert summary["count"] == 1
    assert summary["critical_count"] == 1
    assert summary["items"][0]["notification_id"] == "operational-EXECUTION_BLOCKED"
    assert summary["items"][0]["kind"] == "EXECUTION"
    assert summary["items"][0]["severity"] == "CRITICAL"
    assert summary["items"][0]["blocking"] is True


def test_healthy_operational_observability_does_not_create_incident_notifications():
    from core.operational_runtime import build_operational_runtime
    service = ConfiguredEcosystemService(operational_runtime=build_operational_runtime(__import__("pathlib").Path("/tmp/controlador-notification-test-healthy")))
    service.operational_observability = lambda: {
        "execution": {"state": "READY_DEMO"},
        "recovery": {"state": "SAFE_TO_RESUME"},
        "reconciliation": {"pending_request_ids": [], "unknown_request_ids": []},
        "kill_switch": {"enabled": False},
        "runtime_health": {"state": "OK"},
        "market_data": {"health": "HEALTHY"},
    }

    assert service.notification_summary()["count"] == 0

def test_confirmed_demo_outcomes_persist_idempotently_and_stay_separate_from_study():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from core.p49_outcome_reconciliation import ReconciliationState

    service = ConfiguredEcosystemService()
    snapshot = SimpleNamespace(
        cycle_id="demo-cycle-001",
        source="MT5_DEMO_HISTORY",
        reconciliation_state=ReconciliationState.MATCHED,
        outcome="WIN",
        financial_result=2.6,
        observed_at=datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc),
    )
    service._persist_confirmed_demo_outcome(snapshot)
    service._persist_confirmed_demo_outcome(snapshot)

    stored = service.state_store.load("demo_trade_outcomes")
    statistics = service.statistics()
    assert len(stored) == 1
    assert stored[0]["cycle_id"] == "demo-cycle-001"
    assert statistics["total"] == 0
    assert statistics["study"]["source"] == "MANUAL_STUDY"
    assert statistics["demo"]["source"] == "MT5_DEMO_HISTORY"
    assert statistics["demo"]["mode"] == "DEMO"
    assert statistics["demo"]["total"] == 1
    assert statistics["demo"]["wins"] == 1
    assert statistics["demo"]["net_result"] == 2.6
    assert statistics["demo"]["periods"]["monthly"]["total"] == 1


def test_demo_statistics_ignore_unverified_or_non_history_outcomes():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from core.p49_outcome_reconciliation import ReconciliationState

    service = ConfiguredEcosystemService()
    base = {
        "cycle_id": "ignored",
        "outcome": "WIN",
        "financial_result": 5.0,
        "observed_at": datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc),
    }
    service._persist_confirmed_demo_outcome(SimpleNamespace(
        **base, source="MANUAL_STUDY", reconciliation_state=ReconciliationState.MATCHED
    ))
    service._persist_confirmed_demo_outcome(SimpleNamespace(
        **{**base, "cycle_id": "unverified"}, source="MT5_DEMO_HISTORY",
        reconciliation_state=ReconciliationState.UNVERIFIED
    ))
    assert service.statistics()["demo"]["total"] == 0


def test_demo_outcome_conflict_for_same_cycle_is_not_overwritten():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from core.p49_outcome_reconciliation import ReconciliationState

    service = ConfiguredEcosystemService()
    common = dict(
        cycle_id="demo-cycle-conflict",
        source="MT5_DEMO_HISTORY",
        reconciliation_state=ReconciliationState.MATCHED,
        observed_at=datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc),
    )
    service._persist_confirmed_demo_outcome(SimpleNamespace(
        **common, outcome="WIN", financial_result=2.0
    ))
    try:
        service._persist_confirmed_demo_outcome(SimpleNamespace(
            **common, outcome="LOSS", financial_result=-2.0
        ))
    except RuntimeError as exc:
        assert "contraditório" in str(exc)
    else:
        raise AssertionError("a conflicting result must never overwrite a confirmed cycle")
    assert service.statistics()["demo"]["wins"] == 1
    assert service.statistics()["demo"]["losses"] == 0

