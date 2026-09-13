from __future__ import annotations

import io
import json

from app import application


def request(path: str):
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
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "localhost",
        "wsgi.url_scheme": "http",
    }
    body = b"".join(application(environ, start_response))
    return captured["status"], captured["headers"], json.loads(body)


def test_health_endpoint_exposes_critical_runtime_contract():
    status, headers, payload = request("/api/health")

    assert status == "200 OK"
    assert "application/json" in headers["Content-Type"]
    assert payload["ok"] is True
    assert payload["health"] in {"OK", "WARNING", "CRITICAL"}
    assert isinstance(payload["components"], dict)
    assert isinstance(payload["alerts"], list)
    assert payload["execution_allowed"] is False
    assert payload["real"] == "DESABILITADO"


def test_status_and_risk_remain_fail_closed():
    status, _, payload = request("/api/status")
    assert status == "200 OK"
    assert payload["execution_allowed"] is False
    assert payload["real"] == "DESABILITADO"

    status, _, risk = request("/api/risk")
    assert status == "200 OK"
    assert isinstance(risk["allowed"], bool)
    assert isinstance(risk["reason"], str)
    assert isinstance(risk["configured_limits"], dict)
