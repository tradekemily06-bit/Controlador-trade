from __future__ import annotations

import io
import json

import pytest

from app import application


def request(path: str, *, identity: str | None = None):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        "REMOTE_ADDR": "198.51.100.25",
        "HTTP_HOST": "control.example.test",
        "wsgi.url_scheme": "https",
    }
    if identity is not None:
        environ["HTTP_X_AUTHENTICATED_USER"] = identity
    body = b"".join(application(environ, start_response))
    return captured["status"], captured["headers"], json.loads(body)


@pytest.fixture
def remote_identity_required(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Authenticated-User")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.test")


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/status",
        "/api/memory",
        "/api/statistics",
        "/api/preferences",
        "/api/notifications",
        "/api/notifications/all",
        "/api/risk",
        "/api/connections",
        "/api/learning",
        "/api/learning/resources",
        "/api/learning/sources",
        "/api/learning/observations",
        "/api/learning/activities",
    ],
)
def test_remote_private_get_routes_reject_missing_identity(path, remote_identity_required):
    status, _, payload = request(path)

    assert status == "401 Unauthorized"
    assert "Identidade autenticada necessária" in payload["error"]


def test_remote_private_get_route_rejects_wrong_identity(remote_identity_required):
    status, _, payload = request("/api/risk", identity="other@example.test")

    assert status == "403 Forbidden"
    assert "Identidade autenticada necessária" in payload["error"]


def test_remote_private_get_route_accepts_pinned_identity(remote_identity_required):
    status, _, payload = request("/api/risk", identity="owner@example.test")

    assert status == "200 OK"
    assert isinstance(payload["allowed"], bool)


def test_remote_liveness_probe_remains_public(remote_identity_required):
    status, _, payload = request("/api/health/live")

    assert status == "200 OK"
    assert payload == {"ok": True, "live": True, "service": "controlador"}
