import io
import json

from app import application


def call_app(path, method="GET", payload=None, authorization=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "QUERY_STRING": "",
        "CONTENT_TYPE": "application/json" if payload is not None else "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    if authorization is not None:
        environ["HTTP_AUTHORIZATION"] = authorization
    result = b"".join(application(environ, start_response))
    return captured["status"], json.loads(result)


def test_notification_summary_is_reachable_and_safe():
    status, payload = call_app("/api/notifications")
    assert status == "200 OK"
    assert isinstance(payload["count"], int)
    assert isinstance(payload["critical_count"], int)
    assert isinstance(payload["items"], list)


def test_ecosystem_update_endpoint_fails_closed_without_internal_token(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_UPDATE_TOKEN", raising=False)
    status, payload = call_app(
        "/api/updates",
        method="POST",
        payload={"title": "Atualização de teste", "message": "Nova versão disponível."},
    )
    assert status == "503 Service Unavailable"
    assert payload["error"] == "internal update endpoint is not configured"


def test_ecosystem_update_requires_valid_internal_token(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_UPDATE_TOKEN", "test-internal-token")
    payload = {"title": "Atualização de teste", "message": "Nova versão disponível."}

    status, denied = call_app("/api/updates", method="POST", payload=payload, authorization="Bearer wrong")
    assert status == "403 Forbidden"
    assert denied["error"] == "internal authorization denied"

    status, allowed = call_app("/api/updates", method="POST", payload=payload, authorization="Bearer test-internal-token")
    assert status == "200 OK"
    item = allowed["notification"]
    assert item["kind"] == "SYSTEM_UPDATE"
    assert item["severity"] == "IMPORTANT"


def test_notification_preferences_endpoint_cannot_be_used_as_execution_authority():
    status, payload = call_app(
        "/api/preferences/notifications",
        method="POST",
        payload={"important_enabled": False, "security_enabled": False},
    )
    assert status == "200 OK"
    assert payload["preferences"]["notifications"]["important_enabled"] is False
    assert payload["preferences"]["notifications"]["security_enabled"] is False
