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
    # User-facing analysis preferences must not weaken an execution cycle.
    service.preferences.update(require_closed_candle=False, require_filters=False)
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

    result = service.run_mt5_cycle(symbol="EURUSD", timeframe="5m", limit=20)
    assert result == "runtime-result"
    assert fake.kwargs["automation_policy"].enabled is True
    assert fake.kwargs["confirmed"] is True
    assert fake.kwargs["filters_ok"] is True
    assert fake.kwargs["filters_required"] is True
    assert fake.kwargs["entry_conditions"] == ()
    assert callable(fake.kwargs["automation_readiness_factory"])
    assert callable(fake.kwargs["automation_risk_budget_factory"])


def test_mt5_cycle_rejects_invalid_client_sizing_before_runtime_access():
    service = ConfiguredEcosystemService(execution_provider="paper")
    invalid_requests = (
        {"symbol": "EURUSD", "amount": True},
        {"symbol": "EURUSD", "amount": float("nan")},
        {"symbol": "EURUSD", "amount": float("inf")},
        {"symbol": "EURUSD", "duration_seconds": True},
        {"symbol": "EURUSD", "duration_seconds": 0},
        {"symbol": "EURUSD", "duration_seconds": 86401},
        {"symbol": "EURUSD", "limit": 19},
        {"symbol": "EURUSD", "limit": 501},
    )
    for request in invalid_requests:
        try:
            service.run_mt5_cycle(**request)
        except ValueError:
            continue
        raise AssertionError(f"invalid MT5 cycle request was accepted: {request!r}")


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



def test_mt5_historical_replay_uses_closed_candles_chronologically_without_side_effects():
    from datetime import datetime, timedelta, timezone
    from data.models import Candle

    class FakeMarketAdapter:
        def __init__(self, candles):
            self.candles = candles
            self.request = None

        def fetch_market_data(self, request):
            self.request = request
            return self.candles

    candles = tuple(
        Candle(
            datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
            100 + index, 102 + index, 99 + index, 101 + index, 10,
        )
        for index in range(25)
    )
    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    adapter = FakeMarketAdapter(candles)
    service.mt5_market_adapter = adapter
    before_memory = list(service.memory)

    result = service.replay_mt5_history(symbol="EURUSD", timeframe="5m", limit=25)

    assert adapter.request.symbol == "EURUSD"
    assert adapter.request.timeframe == "5m"
    assert adapter.request.limit == 25
    assert result["candles_replayed"] == 25
    assert len(result["records"]) == 24
    assert result["records"][-1]["timestamp"] == candles[-1].timestamp.isoformat()
    assert result["orders_sent"] is False
    assert result["execution_allowed"] is False
    assert result["lookahead"] is False
    assert service.memory == before_memory


def test_mt5_historical_replay_requires_demo_provider():
    service = ConfiguredEcosystemService(execution_provider="paper")
    try:
        service.replay_mt5_history(symbol="EURUSD", timeframe="5m", limit=25)
    except RuntimeError as exc:
        assert "DEMO" in str(exc)
    else:
        raise AssertionError("historical replay must require the MT5 DEMO provider")

def test_mt5_historical_replay_rejects_out_of_order_candles():
    from datetime import datetime, timedelta, timezone
    from data.models import Candle

    class FakeMarketAdapter:
        def fetch_market_data(self, request):
            return tuple(
                Candle(
                    datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
                    100 + index, 102 + index, 99 + index, 101 + index, 10,
                )
                for index in reversed(range(25))
            )

    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    service.mt5_market_adapter = FakeMarketAdapter()
    try:
        service.replay_mt5_history(symbol="EURUSD", timeframe="5m", limit=25)
    except RuntimeError as exc:
        assert "ordem cronológica" in str(exc)
    else:
        raise AssertionError("replay must reject out-of-order market data")




def test_mt5_signal_scenario_is_hypothetical_and_side_effect_free():
    from datetime import datetime, timedelta, timezone
    from data.models import Candle

    class FakeMarketAdapter:
        def __init__(self, candles):
            self.request = None
            self.candles = candles

        def fetch_market_data(self, request):
            self.request = request
            return self.candles

    candles = tuple(
        Candle(
            datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
            100 + index, 102 + index, 99 + index, 101 + index, 10,
        )
        for index in range(25)
    )
    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    adapter = FakeMarketAdapter(candles)
    service.mt5_market_adapter = adapter
    before_memory = list(service.memory)

    result = service.simulate_mt5_signal_scenario(
        symbol="EURUSD", timeframe="5m", limit=25, minimum_directional_score=80
    )

    assert adapter.request.symbol == "EURUSD"
    assert adapter.request.timeframe == "5m"
    assert adapter.request.limit == 25
    assert result["candles_replayed"] == 25
    assert len(result["records"]) == 24
    assert result["minimum_directional_score"] == 80
    assert result["orders_sent"] is False
    assert result["execution_allowed"] is False
    assert result["pnl_calculated"] is False
    assert result["risk_rules_applied"] is False
    assert result["lookahead"] is False
    assert result["simulation_kind"] == "HISTORICAL_SIGNAL_THRESHOLD_ONLY"
    assert service.memory == before_memory


def test_mt5_signal_scenario_rejects_invalid_confidence_and_non_demo_provider():
    service = ConfiguredEcosystemService(execution_provider="paper")
    try:
        service.simulate_mt5_signal_scenario(
            symbol="EURUSD", timeframe="5m", limit=25, minimum_directional_score=69
        )
    except RuntimeError as exc:
        assert "DEMO" in str(exc)
    else:
        raise AssertionError("signal simulator must require MT5 DEMO")

    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    try:
        service.simulate_mt5_signal_scenario(
            symbol="EURUSD", timeframe="5m", limit=25, minimum_directional_score=69
        )
    except ValueError as exc:
        assert "70 e 95" in str(exc)
    else:
        raise AssertionError("confidence below the allowed range must be rejected")


def test_mt5_signal_scenario_rejects_out_of_order_history():
    from datetime import datetime, timedelta, timezone
    from data.models import Candle

    class FakeMarketAdapter:
        def fetch_market_data(self, request):
            return tuple(
                Candle(
                    datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
                    100 + index, 102 + index, 99 + index, 101 + index, 10,
                )
                for index in reversed(range(25))
            )

    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    service.mt5_market_adapter = FakeMarketAdapter()
    try:
        service.simulate_mt5_signal_scenario(
            symbol="EURUSD", timeframe="5m", limit=25, minimum_directional_score=80
        )
    except RuntimeError as exc:
        assert "ordem cronológica" in str(exc)
    else:
        raise AssertionError("simulator must reject out-of-order market data")



def test_mt5_historical_backtest_is_side_effect_free_and_uses_demo_history():
    from datetime import datetime, timedelta, timezone
    from data.models import Candle

    class FakeMarketAdapter:
        def __init__(self, candles):
            self.request = None
            self.candles = candles

        def fetch_market_data(self, request):
            self.request = request
            return self.candles

    candles = tuple(
        Candle(
            datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
            100 + index, 102 + index, 99 + index, 101 + index, 10,
        )
        for index in range(25)
    )
    service = ConfiguredEcosystemService(execution_provider="ic_markets_mt5_demo")
    adapter = FakeMarketAdapter(candles)
    service.mt5_market_adapter = adapter
    before_memory = list(service.memory)

    result = service.run_mt5_historical_backtest(
        symbol="EURUSD",
        timeframe="5m",
        limit=25,
        stop_distance=0.1,
        take_profit_distance=0.2,
        quantity_units=100,
        spread_price_units=0.01,
        slippage_price_units_per_side=0.001,
        commission_quote_per_unit_round_turn=0.001,
        minimum_directional_score=80,
    )

    assert adapter.request.symbol == "EURUSD"
    assert adapter.request.timeframe == "5m"
    assert adapter.request.limit == 25
    assert result["candles_processed"] == 25
    assert result["orders_sent"] is False
    assert result["execution_allowed"] is False
    assert result["lookahead"] is False
    assert result["simulation_kind"] == "HISTORICAL_OHLC_FIXED_SL_TP"
    assert result["assumptions"]["risk_manager_integrated"] is False
    assert result["assumptions"]["margin_and_leverage_simulated"] is False
    assert service.memory == before_memory


def test_mt5_historical_backtest_rejects_non_demo_provider():
    service = ConfiguredEcosystemService(execution_provider="paper")
    try:
        service.run_mt5_historical_backtest(
            symbol="EURUSD",
            stop_distance=0.1,
            take_profit_distance=0.2,
            quantity_units=100,
            spread_price_units=0.01,
            slippage_price_units_per_side=0,
        )
    except RuntimeError as exc:
        assert "DEMO" in str(exc)
    else:
        raise AssertionError("historical backtest must require MT5 DEMO")




def _service_with_accepted_demo_position(tmp_path):
    from datetime import datetime, timezone
    from core.operational_runtime import build_operational_runtime
    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState

    runtime = build_operational_runtime(tmp_path)
    service = ConfiguredEcosystemService(
        operational_runtime=runtime,
        execution_provider="ic_markets_mt5_demo",
    )
    runtime.execution_ledger.reserve("request-demo-1", cycle_id="cycle-demo-1")
    runtime.execution_ledger.bind_external_id(
        "request-demo-1",
        "123456",
        account_fingerprint="a" * 32,
    )
    runtime.execution_ledger.mark_accepted("request-demo-1")
    runtime.execution_lifecycle.put(ExecutionLifecycleRecord(
        "request-demo-1",
        ExecutionLifecycleState.ACCEPTED,
        datetime.now(timezone.utc),
        "accepted in DEMO",
    ))
    return service, runtime


def test_demo_close_persists_attempt_and_uses_opening_account_fingerprint(tmp_path):
    from execution.ports import ExecutionResult
    service, runtime = _service_with_accepted_demo_position(tmp_path)
    calls = []

    class FakeAdapter:
        def close_position(self, external_id, *, expected_account_fingerprint=None):
            calls.append((external_id, expected_account_fingerprint))
            return ExecutionResult(True, "posição fechada e confirmada", "close-999")

    service.mt5_operational_adapter = FakeAdapter()
    result = service.close_mt5_position(cycle_id="cycle-demo-1", external_id="123456")

    assert result.accepted is True
    assert calls == [("123456", "a" * 32)]
    record = runtime.position_closes.get("request-demo-1")
    assert record.state.value == "CLOSED"
    assert record.close_external_id == "close-999"


def test_demo_close_fails_closed_without_opening_account_fingerprint(tmp_path):
    from datetime import datetime, timezone
    from core.operational_runtime import build_operational_runtime
    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState

    runtime = build_operational_runtime(tmp_path)
    service = ConfiguredEcosystemService(
        operational_runtime=runtime,
        execution_provider="ic_markets_mt5_demo",
    )
    runtime.execution_ledger.reserve("request-demo-2", cycle_id="cycle-demo-2")
    runtime.execution_ledger.bind_external_id("request-demo-2", "123457")
    runtime.execution_ledger.mark_accepted("request-demo-2")
    runtime.execution_lifecycle.put(ExecutionLifecycleRecord(
        "request-demo-2",
        ExecutionLifecycleState.ACCEPTED,
        datetime.now(timezone.utc),
        "accepted without account fingerprint",
    ))
    calls = []

    class FakeAdapter:
        def close_position(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("broker must not be called without opening account fingerprint")

    service.mt5_operational_adapter = FakeAdapter()
    try:
        service.close_mt5_position(cycle_id="cycle-demo-2", external_id="123457")
    except ValueError as exc:
        assert "impressão digital" in str(exc)
    else:
        raise AssertionError("close without opening account fingerprint must be blocked")
    assert calls == []


def test_demo_close_unknown_requires_read_only_reconciliation_before_retry(tmp_path):
    from execution.ports import (
        ExecutionResult,
        PositionCloseObservation,
        PositionCloseObservationStatus,
    )
    service, runtime = _service_with_accepted_demo_position(tmp_path)

    class FakeAdapter:
        close_calls = 0

        def close_position(self, external_id, *, expected_account_fingerprint=None):
            self.close_calls += 1
            if self.close_calls == 1:
                return ExecutionResult(False, "resposta ambígua do broker")
            return ExecutionResult(True, "posição fechada", "close-1000")

        def reconcile_position_close(self, external_id, *, expected_account_fingerprint=None):
            return PositionCloseObservation(
                PositionCloseObservationStatus.OPEN,
                "MT5 confirma que a posição continua aberta",
            )

    adapter = FakeAdapter()
    service.mt5_operational_adapter = adapter
    first = service.close_mt5_position(cycle_id="cycle-demo-1", external_id="123456")
    assert first.accepted is False
    assert runtime.position_closes.get("request-demo-1").state.value == "UNKNOWN"

    reconciliation = service.reconcile_mt5_position_close(
        cycle_id="cycle-demo-1",
        external_id="123456",
    )
    assert reconciliation["state"] == "OPEN"
    assert reconciliation["read_only"] is True
    assert reconciliation["order_sent"] is False

    second = service.close_mt5_position(cycle_id="cycle-demo-1", external_id="123456")
    assert second.accepted is True
    assert adapter.close_calls == 2
    assert [item.attempt for item in runtime.position_closes.history("request-demo-1")] == [1, 2]
