import io
import json

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
    assert data["signal"] == "COMPRA"
    assert data["score"] == 85
    assert data["execution_allowed"] is False


def test_unconfirmed_signal_stays_wait():
    status, data = call_app("/api/analyze", "POST", {"score": 95, "confirmed": False})
    assert status.startswith("200")
    assert data["signal"] == "AGUARDAR"
