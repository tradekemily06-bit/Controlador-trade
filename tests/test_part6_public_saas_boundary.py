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


def test_public_saas_blocks_multi_instance_before_generic_routes(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)
    monkeypatch.setenv("CONTROLADOR_MULTI_INSTANCE", "1")

    status, payload = _request("/api/health")

    assert status.startswith("503 ")
    assert "multi-instance" in payload["error"]


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



def test_replay_endpoint_rejects_excessive_case_count(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: False)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)
    cases = json.dumps({"cases": [{} for _ in range(app.MAX_REPLAY_CASES + 1)]}).encode("utf-8")
    captured = {}
    def start_response(status, headers):
        captured["status"] = status
    environ = {
        "REQUEST_METHOD": "POST", "PATH_INFO": "/api/replay", "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(cases)), "wsgi.input": io.BytesIO(cases), "REMOTE_ADDR": "127.0.0.1",
    }
    payload = json.loads(b"".join(app.application(environ, start_response)))
    assert captured["status"].startswith("400 ")
    assert payload["error"] == "Entrada inválida"


def test_replay_endpoint_rejects_excessive_case_count_against_default_limit(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: False)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)
    cases = json.dumps({"cases": [{} for _ in range(app.MAX_REPLAY_CASES + 1)]}).encode("utf-8")
    captured = {}
    def start_response(status, headers):
        captured["status"] = status
    environ = {
        "REQUEST_METHOD": "POST", "PATH_INFO": "/api/replay", "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(cases)), "wsgi.input": io.BytesIO(cases), "REMOTE_ADDR": "127.0.0.1",
    }
    payload = json.loads(b"".join(app.application(environ, start_response)))
    assert captured["status"].startswith("400 ")
    assert payload["error"] == "Entrada inválida"


def test_public_saas_audit_backend_failure_returns_single_fail_closed_response(monkeypatch):
    monkeypatch.setattr(app, "saas_public_mode", lambda: True)
    monkeypatch.setattr(app.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app.AUDIT, "record", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("audit down")))

    calls = []

    def start_response(status, headers):
        calls.append(status)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/api/health",
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
