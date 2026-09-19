from __future__ import annotations

import io
import json

import app


def _request(path: str, method: str = "GET"):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        "REMOTE_ADDR": "127.0.0.1",
        "controlador.trusted_subject_id": "user-a",
        "controlador.trusted_tenant_id": "tenant-a",
        "controlador.trusted_role": "member",
    }
    body = b"".join(app.application(environ, start_response))
    return captured["status"], json.loads(body)


def test_public_saas_blocks_unscoped_learning_endpoint(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)

    status, payload = _request("/api/learning/activities", "POST")

    assert status.startswith("503 ")
    assert "tenant/subject-scoped" in payload["error"]


def test_public_saas_blocks_unscoped_preferences_endpoint(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)

    status, payload = _request("/api/preferences")

    assert status.startswith("503 ")
    assert "tenant/subject-scoped" in payload["error"]

