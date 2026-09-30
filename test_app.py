import io
import json
from types import SimpleNamespace

from app import application


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
        "wsgi.input": io.BytesIO(body),
    }
    result = b"".join(application(environ, start_response))
    return captured["status"], json.loads(result)


def test_health_is_simulation_only():
    status, data = call_app("/api/health")
    assert status.startswith("200")
    assert data["mode"] == "SIMULACAO"
    assert data["execution"] == "bloqueada_por_padrao"


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
        decision=SimpleNamespace(decision="AGUARDAR", reason="blocked"),
        analysis=SimpleNamespace(signal=SimpleNamespace(value="AGUARDAR"), score=0),
        snapshot=SimpleNamespace(market_context=None),
        market_data=SimpleNamespace(source="IC Markets MT5 DEMO", candles=(1, 2, 3)),
        senior_context=SimpleNamespace(cycle_id="senior-cycle-001"),
    )
    cycle = SimpleNamespace(
        orchestration=orchestration,
        execution=execution,
        plan=SimpleNamespace(request_id="req-001"),
        automation_lifecycle=None,
    )
    fake_result = SimpleNamespace(stopped=True, stop_reason="blocked", cycles=(cycle,))
    monkeypatch.setattr(app.SERVICE, "run_mt5_cycle", lambda **kwargs: fake_result)

    status, data = call_app(
        "/api/runtime/cycle",
        "POST",
        {"symbol": "EURUSD", "timeframe": "5m", "limit": 3, "amount": 0.01, "duration_seconds": 60},
    )

    assert status.startswith("200")
    assert data["runtime"]["cycle_id"] == "senior-cycle-001"
    assert data["runtime"]["request_id"] == "req-001"
    assert data["execution_allowed"] is False


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


def test_application_uses_mt5_demo_as_canonical_default_executor():
    import app
    from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter

    assert isinstance(app.EXECUTOR, ICMarketsMT5DemoAdapter)
