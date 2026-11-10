from __future__ import annotations

import io
import json

import app as app_module
from core.operational_runtime import build_operational_runtime
from integration.ecosystem_service import EcosystemService


def _post_kill_switch(*, identity: str | None, confirmed: bool = True, reason: str = "parada manual"):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = json.dumps({"confirmed": confirmed, "reason": reason}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/runtime/kill-switch/activate",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(body),
        "REMOTE_ADDR": "198.51.100.25",
        "HTTP_HOST": "control.example.test",
        "wsgi.url_scheme": "https",
    }
    if identity is not None:
        environ["HTTP_X_AUTHENTICATED_USER"] = identity
    payload = b"".join(app_module.application(environ, start_response))
    return captured["status"], json.loads(payload)


def _configure_remote_runtime(monkeypatch, tmp_path):
    runtime = build_operational_runtime(tmp_path)
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Authenticated-User")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.test")
    monkeypatch.setattr(app_module, "OPERATIONAL_RUNTIME", runtime)
    monkeypatch.setattr(app_module, "SERVICE", EcosystemService(operational_runtime=runtime))
    return runtime


def test_kill_switch_activation_requires_authenticated_owner(monkeypatch, tmp_path):
    runtime = _configure_remote_runtime(monkeypatch, tmp_path)

    status, payload = _post_kill_switch(identity=None)

    assert status == "401 Unauthorized"
    assert payload["execution_allowed"] is False
    assert runtime.kill_switch.state.enabled is False


def test_kill_switch_activation_rejects_wrong_identity(monkeypatch, tmp_path):
    runtime = _configure_remote_runtime(monkeypatch, tmp_path)

    status, payload = _post_kill_switch(identity="other@example.test")

    assert status == "403 Forbidden"
    assert payload["execution_allowed"] is False
    assert runtime.kill_switch.state.enabled is False


def test_kill_switch_activation_persists_and_blocks_runtime(monkeypatch, tmp_path):
    runtime = _configure_remote_runtime(monkeypatch, tmp_path)

    status, payload = _post_kill_switch(identity="owner@example.test")

    assert status == "200 OK"
    assert payload["activated"] is True
    assert payload["execution_allowed"] is False
    assert payload["kill_switch"]["state"] == "ACTIVE"
    assert runtime.kill_switch.state.enabled is True
    assert runtime.kill_switch.state.reason == "parada manual"
    assert (tmp_path / "operational-safety.json").exists()


def test_kill_switch_activation_requires_explicit_confirmation(monkeypatch, tmp_path):
    runtime = _configure_remote_runtime(monkeypatch, tmp_path)

    status, payload = _post_kill_switch(identity="owner@example.test", confirmed=False)

    assert status == "400 Bad Request"
    assert payload["execution_allowed"] is False
    assert runtime.kill_switch.state.enabled is False


def test_kill_switch_activation_requires_nonempty_bounded_reason(monkeypatch, tmp_path):
    runtime = _configure_remote_runtime(monkeypatch, tmp_path)

    status, payload = _post_kill_switch(identity="owner@example.test", reason=" " * 241)

    assert status == "400 Bad Request"
    assert payload["execution_allowed"] is False
    assert runtime.kill_switch.state.enabled is False
