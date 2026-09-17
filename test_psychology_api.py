import io
import json

from app import application


def call_app(path, method="GET", payload=None, *, environ_extra=None):
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
        "REMOTE_ADDR": "127.0.0.1",
    }
    if environ_extra:
        environ.update(environ_extra)
    result = b"".join(application(environ, start_response))
    return captured["status"], json.loads(result)


def test_psychology_status_exposes_parallel_non_authority_contract():
    status, data = call_app("/api/psychology/status")
    assert status.startswith("200")
    assert data["execution_authority"] is False
    assert data["decision_authority"] is False
    assert data["role"] == "parallel_behavioral_protection"


def test_psychology_check_in_never_authorizes_trading():
    status, data = call_app(
        "/api/psychology/check-in",
        "POST",
        {"emotional_state": "calm", "urge_to_trade": 1, "recent_losses": 0, "fatigue": 1, "confidence": 5, "rule_adherence": 10},
    )
    assert status.startswith("200")
    assert data["trading_authorized"] is False
    assert data["enabled"] is True


def test_advanced_psychology_never_authorizes_trading():
    status, data = call_app(
        "/api/psychology/advanced",
        "POST",
        {"trades_count": 5, "losses": 3, "wins": 2, "consecutive_losses": 2, "urge_to_trade": 8, "rule_breaks": 1},
    )
    assert status.startswith("200")
    assert data["trading_authorized"] is False
    assert "evidence" in data


def test_public_saas_psychology_fails_closed_without_tenant_data_plane(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    status, data = call_app(
        "/api/psychology/status",
        "GET",
        environ_extra={
            "controlador.trusted_subject_id": "user-1",
            "controlador.trusted_tenant_id": "tenant-1",
            "controlador.trusted_role": "user",
        },
    )
    assert status.startswith("503")
    assert data["error"] == "Serviço SaaS indisponível até que o armazenamento seguro esteja configurado."
