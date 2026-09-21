from __future__ import annotations

import io
import json

import app
from security.http_identity import current_trusted_identity


def _request(path: str = "/api/health", method: str = "GET"):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        "REMOTE_ADDR": "127.0.0.1",
    }
    body = b"".join(app.application(environ, start_response))
    return captured["status"], json.loads(body)


def test_request_identity_is_cleared_after_successful_request(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)

    status, payload = _request()

    assert status.startswith("200 ")
    assert payload["ok"] is True
    assert current_trusted_identity() is None


def test_request_identity_is_cleared_after_identity_failure(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)

    # First request establishes an identity. The second request must not inherit it.
    _request()
    assert current_trusted_identity() is None

    captured = {}

    def start_response(status, headers):
        captured["status"] = status

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/api/status",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        "REMOTE_ADDR": "127.0.0.1",
    }
    body = b"".join(app.application(environ, start_response))

    assert captured["status"].startswith("403 ")
    assert json.loads(body)["error"] == "Acesso negado"
    assert current_trusted_identity() is None


def test_public_saas_static_response_fails_closed_before_start_response_on_audit_failure(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app.AUDIT, "record", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("audit down")))

    calls = []

    def start_response(status, headers):
        calls.append(status)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        "REMOTE_ADDR": "127.0.0.1",
        "controlador.trusted_subject_id": "user-a",
        "controlador.trusted_tenant_id": "tenant-a",
        "controlador.trusted_role": "member",
    }
    body = b"".join(app.application(environ, start_response))

    assert calls == ["503 Service Unavailable"]
    assert json.loads(body)["error"] == "serviço de auditoria indisponível"
    assert current_trusted_identity() is None
