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


def call(path: str, method: str = "GET", trusted: bool = False) -> tuple[str, dict]:
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
    if trusted:
        environ["controlador.trusted_subject_id"] = "user-a"
        environ["controlador.trusted_tenant_id"] = "tenant-a"
        environ["controlador.trusted_role"] = "user"
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


def test_public_saas_does_not_expose_global_state_after_identity_is_trusted(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    for path in ("/api/memory", "/api/statistics", "/api/preferences"):
        status, payload = call(path, trusted=True)
        assert status == "503 Service Unavailable", (path, status, payload)
        assert "tenant/subject-scoped" in payload["error"]

    for path in ("/api/status", "/api/news", "/api/connections", "/api/saas/status"):
        status, payload = call(path, trusted=True)
        assert status == "200 OK", (path, status, payload)


def test_every_stateful_public_saas_route_fails_closed_without_durable_scope(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    for method, path in sorted(app.PUBLIC_SAAS_OWNER_SCOPED):
        status, payload = call(path, method=method, trusted=True)
        assert status == "503 Service Unavailable", (method, path, status, payload)
        assert "tenant" in payload["error"].lower() or "scoped" in payload["error"].lower()


def test_public_saas_generic_routes_are_explicitly_minimal(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    for method, path in sorted(app.PUBLIC_SAAS_GENERIC):
        if path == "/api/health":
            status, payload = call(path, method=method, trusted=False)
        else:
            status, payload = call(path, method=method, trusted=True)
        assert status == "200 OK", (method, path, status, payload)


def test_public_saas_health_is_minimal_and_does_not_expose_system_state(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    status, payload = call("/api/health")
    assert status == "200 OK"
    assert payload == {"ok": True} or set(payload) == {"ok", "request_id"}
    assert "production_storage" not in payload
    assert "trusted_identity_provider" not in payload
