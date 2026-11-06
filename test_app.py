import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import application
from data.models import Candle


def call_app(path, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(body)),
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.input": io.BytesIO(body),
    }
    result = b"".join(application(environ, start_response))
    return captured["status"], json.loads(result)


def test_health_is_simulation_only():
    status, data = call_app("/api/health")
    assert status.startswith("200")
    assert data["mode"] == "SIMULACAO"
    assert data["execution"] == "bloqueada_por_padrao"


def test_preferences_api_persists_selected_mode_without_real_authority():
    status, data = call_app("/api/preferences", "POST", {"selected_mode": "REAL"})
    assert status.startswith("200")
    assert data["preferences"]["selected_mode"] == "REAL"
    assert data["preferences"]["real_execution_enabled"] is False


def test_analyze_uses_core_engine():
    status, data = call_app(
        "/api/analyze",
        "POST",
        {"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"},
    )
    assert status.startswith("200")
    assert data["signal"] == "AGUARDAR"
    assert data["score"] == 85
    assert data["execution_allowed"] is False


def test_unconfirmed_signal_stays_wait():
    status, data = call_app("/api/analyze", "POST", {"score": 95, "confirmed": False})
    assert status.startswith("200")
    assert data["signal"] == "AGUARDAR"


def test_runtime_cycle_exposes_authoritative_cycle_lineage(monkeypatch):
    import app

    execution = SimpleNamespace(accepted=False, status=SimpleNamespace(value="BLOCKED"), message="blocked", external_id=None)
    orchestration = SimpleNamespace(
        timestamp=datetime(2026, 10, 16, 12, tzinfo=timezone.utc),
        decision=SimpleNamespace(decision="AGUARDAR", reason="blocked"),
        analysis=SimpleNamespace(
            signal=SimpleNamespace(value="AGUARDAR"),
            score=50.0,
            reason="blocked",
            confirmed=False,
            symbol="EURUSD",
            timeframe="5m",
        ),
        quality=SimpleNamespace(score=1.0, level=SimpleNamespace(value="FRACA"), actionable=False),
        snapshot=SimpleNamespace(market_context=None),
        market_data=SimpleNamespace(
            source="IC Markets MT5 DEMO",
            candles=tuple(
                Candle(datetime(2026, 10, 16, 11, tzinfo=timezone.utc) + timedelta(minutes=i), 100, 101, 99, 100, 1)
                for i in range(3)
            ),
        ),
        senior_context=SimpleNamespace(cycle_id="senior-cycle-001"),
    )
    cycle = SimpleNamespace(
        orchestration=orchestration,
        execution=execution,
        plan=SimpleNamespace(request_id="req-001"),
        automation_lifecycle=None,
    )
    fake_result = SimpleNamespace(stopped=True, stop_reason="blocked", cycles=(cycle,))
    monkeypatch.setattr(app.SERVICE, "get_preferences", lambda: {"selected_mode": "DEMO", "leverage_enabled": False})
    received = {}
    monkeypatch.setattr(app.SERVICE, "run_mt5_cycle", lambda **kwargs: received.update(kwargs) or fake_result)
    monkeypatch.setattr(app.SERVICE, "schedule_mt5_timed_exit", lambda cycle, duration_seconds: {"state": "NOT_APPLICABLE", "scheduled": False, "message": "sem execução aceita"})

    status, data = call_app(
        "/api/runtime/cycle",
        "POST",
        {"symbol": "EURUSD", "timeframe": "5m", "limit": 20, "amount": 0.01, "duration_seconds": 60, "confirmed": False, "filters_ok": False, "entry_conditions": ["client-asserted"]},
    )

    assert status.startswith("200")
    assert received == {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "limit": 20,
        "amount": 0.01,
        "duration_seconds": 60,
    }
    assert data["runtime"]["cycle_id"] == "senior-cycle-001"
    assert data["runtime"]["request_id"] == "req-001"
    assert data["runtime"]["position_close_policy"] == "MANUAL_EXPLICIT"
    assert data["runtime"]["duration_seconds_applied"] is False
    assert data["runtime"]["timed_exit"]["state"] == "NOT_APPLICABLE"
    assert data["execution_allowed"] is False



def test_runtime_cycle_rejects_boolean_sizing_and_invalid_limits_before_service(monkeypatch):
    import app

    monkeypatch.setattr(app.SERVICE, "get_preferences", lambda: {"selected_mode": "DEMO", "leverage_enabled": False})
    monkeypatch.setattr(app.SERVICE, "run_mt5_cycle", lambda **kwargs: (_ for _ in ()).throw(AssertionError("service must not be called")))
    invalid_payloads = (
        {"symbol": "EURUSD", "amount": True},
        {"symbol": "EURUSD", "duration_seconds": True},
        {"symbol": "EURUSD", "limit": True},
        {"symbol": "EURUSD", "limit": 3},
        {"symbol": "EURUSD", "amount": float("nan")},
        {"symbol": "EURUSD", "duration_seconds": 86401},
    )
    for payload in invalid_payloads:
        status, data = call_app("/api/runtime/cycle", "POST", payload)
        assert status.startswith("400"), (payload, status, data)


def test_runtime_close_uses_cycle_bound_durable_close_service(monkeypatch):
    import app

    calls = []
    monkeypatch.setattr(
        app.SERVICE,
        "close_mt5_position",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
            accepted=False,
            message="resposta ambígua; reconciliação necessária",
            external_id=None,
        ),
    )
    monkeypatch.setattr(
        app.SERVICE,
        "reconcile_mt5_cycle",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("opening-order reconciliation is not close evidence")),
    )

    status, data = call_app(
        "/api/runtime/close",
        "POST",
        {"cycle_id": "cycle-1", "external_id": "external-1"},
    )

    assert status.startswith("200")
    assert calls == [{"cycle_id": "cycle-1", "external_id": "external-1"}]
    assert data["closed"] is False
    assert data["close_state"] == "UNKNOWN"
    assert data["reconciliation"] is None


def test_runtime_close_reconciliation_route_is_read_only(monkeypatch):
    import app

    observed = {}
    monkeypatch.setattr(
        app.SERVICE,
        "reconcile_mt5_position_close",
        lambda **kwargs: observed.update(kwargs) or {
            "request_id": "request-1",
            "external_id": "ticket-1",
            "state": "OPEN",
            "message": "position still open",
            "read_only": True,
            "order_sent": False,
        },
    )

    status, data = call_app(
        "/api/runtime/close/reconcile",
        "POST",
        {"cycle_id": "cycle-1", "external_id": "ticket-1"},
    )
    assert status.startswith("200")
    assert observed == {"cycle_id": "cycle-1", "external_id": "ticket-1"}
    assert data["close_reconciliation"]["read_only"] is True
    assert data["close_reconciliation"]["order_sent"] is False


def test_runtime_close_reconciliation_rejects_coerced_identity_types():
    status, data = call_app(
        "/api/runtime/close/reconcile",
        "POST",
        {"cycle_id": None, "external_id": "ticket-1"},
    )
    assert status.startswith("400")
    assert "cycle_id" in data["error"]

def test_runtime_reconcile_forwards_cycle_lineage(monkeypatch):
    import app

    observed = {}

    def reconcile(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            cycle_id=kwargs["cycle_id"],
            terminal_state="COMPLETED",
            outcome="UNKNOWN",
            financial_result=None,
            reconciliation_state=SimpleNamespace(value="UNVERIFIED"),
        )

    monkeypatch.setattr(app.SERVICE, "reconcile_mt5_cycle", reconcile)

    status, data = call_app(
        "/api/runtime/reconcile",
        "POST",
        {"cycle_id": "senior-cycle-001", "external_id": "external-123"},
    )

    assert status.startswith("200")
    assert observed == {"cycle_id": "senior-cycle-001", "external_id": "external-123"}
    assert data["runtime_reconciliation"]["cycle_id"] == "senior-cycle-001"
    assert data["runtime_reconciliation"]["reconciliation_state"] == "UNVERIFIED"


def test_application_uses_safe_provider_by_default():
    import app
    from execution.paper import PaperExecutor

    assert isinstance(app.EXECUTOR, PaperExecutor)


def test_remote_mutation_is_blocked_without_trusted_identity():
    body = json.dumps({"symbol": "EURUSD", "timeframe": "5m"}).encode()
    captured = {}

    def start_response(status, headers):
        captured["status"] = status

    environ = {
        "PATH_INFO": "/api/preferences",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "REMOTE_ADDR": "10.0.0.25",
        "wsgi.input": io.BytesIO(body),
    }
    result = b"".join(application(environ, start_response))
    assert captured["status"].startswith("503")
    assert json.loads(result)["error"] == "trusted remote identity provider is not configured"



def test_fiscal_pending_api_returns_conflict_for_duplicate_reference(tmp_path, monkeypatch):
    import app
    from finance.fiscal_pending_queue import FiscalPendingQueue

    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "api-test-owner")
    fiscal_path = tmp_path / "fiscal.sqlite3"
    monkeypatch.setattr(app, "FISCAL_RESERVE_DB", fiscal_path)
    monkeypatch.setattr(app, "FISCAL_PENDING_QUEUE", FiscalPendingQueue(str(fiscal_path)))
    monkeypatch.setattr(app, "FISCAL_RESERVE", __import__("finance.fiscal_reserve", fromlist=["FiscalReserve"]).FiscalReserve(str(fiscal_path)))
    payload = {
        "reference": "API-DUPLICATE-001",
        "original_amount": 125.50,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-10-30",
    }

    created_status, created = call_app("/api/fiscal-reserve/pending", "POST", payload)
    duplicate_status, duplicate = call_app("/api/fiscal-reserve/pending", "POST", payload)

    assert created_status.startswith("201")
    assert created["reserve_calculated"] is False
    assert duplicate_status.startswith("409")
    assert duplicate["error"] == "Já existe uma pendência com essa referência."


def test_mt5_historical_replay_api_is_read_only_and_returns_service_result(monkeypatch):
    import app

    expected = {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "candles_replayed": 24,
        "records": [],
        "orders_sent": False,
        "execution_allowed": False,
        "lookahead": False,
    }
    monkeypatch.setattr(app.SERVICE, "replay_mt5_history", lambda **kwargs: expected)
    status, data = call_app(
        "/api/replay/mt5",
        "POST",
        {"symbol": "EURUSD", "timeframe": "5m", "limit": 25},
    )
    assert status.startswith("200")
    assert data == expected
    assert data["orders_sent"] is False
    assert data["execution_allowed"] is False


def test_mt5_historical_signal_simulator_api_is_read_only(monkeypatch):
    import app

    expected = {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "candles_replayed": 24,
        "records": [],
        "orders_sent": False,
        "execution_allowed": False,
        "pnl_calculated": False,
        "risk_rules_applied": False,
        "lookahead": False,
    }
    monkeypatch.setattr(app.SERVICE, "simulate_mt5_signal_scenario", lambda **kwargs: expected)
    status, data = call_app(
        "/api/simulator/mt5",
        "POST",
        {
            "symbol": "EURUSD",
            "timeframe": "5m",
            "limit": 25,
            "minimum_directional_score": 80,
        },
    )
    assert status.startswith("200")
    assert data == expected
    assert data["orders_sent"] is False
    assert data["execution_allowed"] is False
    assert data["pnl_calculated"] is False



def test_mt5_historical_backtest_api_is_read_only(monkeypatch):
    import app

    expected = {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "candles_processed": 25,
        "trades": [],
        "orders_sent": False,
        "execution_allowed": False,
        "lookahead": False,
    }
    monkeypatch.setattr(app.SERVICE, "run_mt5_historical_backtest", lambda **kwargs: expected)
    status, data = call_app(
        "/api/simulator/mt5/backtest",
        "POST",
        {
            "symbol": "EURUSD",
            "timeframe": "5m",
            "limit": 25,
            "stop_distance": 0.1,
            "take_profit_distance": 0.2,
            "quantity_units": 100,
            "contract_multiplier": 1.0,
            "spread_price_units": 0.01,
            "slippage_price_units_per_side": 0.001,
            "commission_quote_per_unit_round_turn": 0.001,
            "minimum_directional_score": 80,
        },
    )
    assert status.startswith("200")
    assert data == expected
    assert data["orders_sent"] is False
    assert data["execution_allowed"] is False
    assert data["lookahead"] is False



def test_mt5_position_recovery_api_is_authenticated_and_read_only(monkeypatch):
    import app

    expected = [{
        "cycle_id": "cycle-demo-recovery",
        "external_id": "ticket-900",
        "recovery_state": "RECONCILIATION_REQUIRED",
        "broker_query_performed": False,
        "order_sent": False,
    }]
    monkeypatch.setattr(app, "_authorize_remote_mutation", lambda environ: (True, "trusted"))
    monkeypatch.setattr(app.SERVICE, "list_mt5_position_recovery", lambda: expected)

    status, data = call_app("/api/runtime/positions/recovery")

    assert status.startswith("200")
    assert data["positions"] == expected
    assert data["read_only"] is True
    assert data["broker_query_performed"] is False
    assert data["orders_sent"] is False


