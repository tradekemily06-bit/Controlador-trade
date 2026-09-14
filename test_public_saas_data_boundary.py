from __future__ import annotations

import io
import json

import app


SENSITIVE_READS = (
    "/api/preferences",
    "/api/notifications",
    "/api/notifications/all",
    "/api/memory",
    "/api/statistics",
    "/api/risk",
    "/api/news",
    "/api/connections",
    "/api/learning",
    "/api/learning/resources",
    "/api/learning/sources",
    "/api/learning/observations",
    "/api/learning/activities",
    "/api/saas/status",
)


def call(path: str, method: str = "GET") -> tuple[str, dict]:
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.input": io.BytesIO(b""),
    }
    body = b"".join(app.application(environ, start_response))
    return str(captured["status"]), json.loads(body.decode("utf-8"))


def test_public_saas_sensitive_reads_require_trusted_identity(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    for path in SENSITIVE_READS:
        status, payload = call(path)
        assert status == "403 Forbidden", (path, status, payload)
        assert "request_id" in payload


def test_public_saas_mutation_requires_trusted_identity(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    status, payload = call("/api/outcome", method="POST")
    assert status == "403 Forbidden"
    assert "request_id" in payload
