from pathlib import Path

import app as app_module


ROOT = Path(__file__).resolve().parents[1]


def test_demo_position_recovery_endpoint_is_authenticated_and_read_only():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index('if path == "/api/runtime/positions/recovery" and method == "GET":')
    end = source.index('if path == "/api/runtime/close/reconcile" and method == "POST":', start)
    route = source[start:end]

    assert "_authorize_remote_mutation(environ)" in route
    assert "SERVICE.list_mt5_position_recovery()" in route
    assert '"positions": positions' in route
    assert '"count": len(positions)' in route
    assert '"read_only": True' in route
    assert '"broker_query_performed": False' in route
    assert '"orders_sent": False' in route
    assert "order_send" not in route
    assert "close_mt5_position" not in route


def test_demo_position_recovery_inventory_does_not_infer_live_open_state():
    source = (ROOT / "integration" / "ecosystem_configuration_runtime.py").read_text(encoding="utf-8")
    start = source.index("def list_mt5_position_recovery")
    end = source.index("def list_mt5_timed_exits", start)
    method = source[start:end]

    assert '"BLOCKED_ACCOUNT_IDENTITY"' in method
    assert '"BROKER_CONFIRMED_OPEN"' in method
    assert '"RECONCILIATION_REQUIRED"' in method
    assert '"broker_query_performed": False' in method
    assert '"order_sent": False' in method
    assert "reconcile_position_close" not in method
    assert "close_position" not in method


def test_native_mt5_recovery_routes_are_loopback_only_and_require_local_mutations():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    helper = source.split("def _authorize_local_runtime", 1)[1].split("def _authorize_internal_update", 1)[0]
    assert 'REMOTE_ADDR' in helper
    assert '{"127.0.0.1", "::1"}' in helper
    assert "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED" in helper
    assert "CONTROLADOR_LOCAL_MUTATION_HOSTS" in helper
    assert "CONTROLADOR_TRUSTED_IDENTITY_HEADER" in helper
    assert "trusted remote identity cannot use local runtime routes" in helper
    assert 'if not host or host not in allowed_hosts' in helper

    for route_path in (
        "/api/runtime/positions/recovery/local",
        "/api/runtime/close/local/reconcile",
        "/api/runtime/close/local",
    ):
        route = source.split(f'if path == "{route_path}"', 1)[1].split("\n        if path ==", 1)[0]
        assert "_authorize_local_runtime(environ)" in route

def test_remote_recovery_and_close_routes_still_require_trusted_identity():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    for route_path in (
        "/api/runtime/positions/recovery",
        "/api/runtime/close/reconcile",
        "/api/runtime/close",
    ):
        route = source.split(f'if path == "{route_path}"', 1)[1].split("\n        if path ==", 1)[0]
        assert "_authorize_remote_mutation(environ)" in route


def test_native_recovery_routes_keep_explicit_response_contracts_and_fresh_close_preflight():
    api = (ROOT / "app.py").read_text(encoding="utf-8")
    integration = (ROOT / "integration" / "ecosystem_configuration_runtime.py").read_text(encoding="utf-8")
    inventory = api.split('if path == "/api/runtime/positions/recovery/local" and method == "GET":', 1)[1].split(
        'if path == "/api/runtime/close/local/reconcile" and method == "POST":', 1
    )[0]
    reconcile = api.split('if path == "/api/runtime/close/local/reconcile" and method == "POST":', 1)[1].split(
        'if path == "/api/runtime/close/local" and method == "POST":', 1
    )[0]
    close = api.split('if path == "/api/runtime/close/local" and method == "POST":', 1)[1].split(
        'if path == "/api/runtime/positions/recovery" and method == "GET":', 1
    )[0]
    close_service = integration.split("def close_mt5_position", 1)[1].split(
        "def reconcile_mt5_position_close", 1
    )[0]

    assert '"positions": positions' in inventory
    assert '"read_only": True' in inventory
    assert '"broker_query_performed": False' in inventory
    assert '"close_reconciliation": result' in reconcile
    assert '"closed": close_result.accepted' in close
    assert '"close_state": "CLOSED" if close_result.accepted else "UNKNOWN"' in close
    assert "reconcile_position_close(" in close_service
    assert "if current.state is not PositionCloseState.OPEN:" in close_service
    assert close_service.index("reconcile_position_close(") < close_service.index("close_position(")
    assert "store.begin(request_id, external_id.strip())" in close_service


def test_local_runtime_authorization_does_not_trust_forwarded_client_headers():
    api = (ROOT / "app.py").read_text(encoding="utf-8")
    helper = api.split("def _authorize_local_runtime", 1)[1].split("def _authorize_internal_update", 1)[0]
    assert 'environ.get("REMOTE_ADDR")' in helper
    assert "HTTP_X_FORWARDED_FOR" not in helper
    assert 'environ.get("HTTP_HOST")' in helper


def test_local_runtime_authorization_accepts_only_explicit_same_host_ea_requests(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "Cf-Access-Authenticated-User-Email")

    allowed, reason = app_module._authorize_local_runtime({
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "127.0.0.1:8000",
    })
    assert (allowed, reason) == (True, "local")

    proxied, proxy_reason = app_module._authorize_local_runtime({
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "127.0.0.1:8000",
        "HTTP_CF_ACCESS_AUTHENTICATED_USER_EMAIL": "owner@example.com",
    })
    assert proxied is False
    assert proxy_reason == "trusted remote identity cannot use local runtime routes"

    public_peer, peer_reason = app_module._authorize_local_runtime({
        "REMOTE_ADDR": "203.0.113.20",
        "HTTP_HOST": "127.0.0.1:8000",
    })
    assert public_peer is False
    assert peer_reason == "local runtime requires loopback"

    public_host, host_reason = app_module._authorize_local_runtime({
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "control.example",
    })
    assert public_host is False
    assert host_reason == "local Host is not allowed"


def test_local_runtime_authorization_supports_bracketed_ipv6_loopback(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "Cf-Access-Authenticated-User-Email")

    allowed, reason = app_module._authorize_local_runtime({
        "REMOTE_ADDR": "::1",
        "HTTP_HOST": "[::1]:8000",
    })
    assert (allowed, reason) == (True, "local")


def test_local_runtime_authorization_fails_closed_when_mutations_are_not_enabled(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", raising=False)
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "Cf-Access-Authenticated-User-Email")

    allowed, reason = app_module._authorize_local_runtime({
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "127.0.0.1:8000",
    })
    assert allowed is False
    assert reason == "local mutations are disabled"


def test_remote_mutation_authorization_accepts_bracketed_ipv6_loopback_host(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]")

    allowed, reason = app_module._authorize_remote_mutation({
        "REMOTE_ADDR": "::1",
        "HTTP_HOST": "[::1]:8000",
    })

    assert allowed is True
    assert reason == "local"


def test_local_ea_post_routes_reach_their_own_loopback_authorization_before_remote_gate():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    gate = source.split("def application(environ, start_response):", 1)[1].split("\n    try:", 1)[0]

    assert '"/api/runtime/close/local/reconcile"' in gate
    assert '"/api/runtime/close/local"' in gate
    assert 'path not in local_ea_post_paths' in gate
    assert 'if method == "POST" and path != "/api/updates" and path not in local_ea_post_paths and not path.startswith("/api/assistant/"):' in gate

    for route_path in (
        "/api/runtime/close/local/reconcile",
        "/api/runtime/close/local",
    ):
        route = source.split(f'if path == "{route_path}"', 1)[1].split("\n        if path ==", 1)[0]
        assert "_authorize_local_runtime(environ)" in route


def _invoke_local_close_api(monkeypatch, path, *, remote_addr="127.0.0.1", host="127.0.0.1:8000", access_identity=None):
    import io
    import json

    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "Cf-Access-Authenticated-User-Email")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATION_HOSTS", "localhost,127.0.0.1,[::1]")
    monkeypatch.setattr(app_module.SECURITY, "allow", lambda environ: True)
    monkeypatch.setattr(app_module.SECURITY, "headers", lambda request_id, **kwargs: [])
    monkeypatch.setattr(app_module, "_audit", lambda *args, **kwargs: None)

    raw = json.dumps({"cycle_id": "cycle-1", "external_id": "ticket-1"}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "REMOTE_ADDR": remote_addr,
        "HTTP_HOST": host,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    if access_identity is not None:
        environ["HTTP_CF_ACCESS_AUTHENTICATED_USER_EMAIL"] = access_identity
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app_module.application(environ, start_response))
    return response["status"], json.loads(body)


def test_local_ea_close_and_reconcile_work_when_remote_access_is_required(monkeypatch):
    calls = []

    class CloseResult:
        accepted = True
        message = "closed"
        external_id = "ticket-1-close"

    def reconcile(**kwargs):
        calls.append(("reconcile", kwargs))
        return {"state": "OPEN", "read_only": True}

    def close(**kwargs):
        calls.append(("close", kwargs))
        return CloseResult()

    monkeypatch.setattr(app_module.SERVICE, "reconcile_mt5_position_close", reconcile)
    monkeypatch.setattr(app_module.SERVICE, "close_mt5_position", close)

    for path in ("/api/runtime/close/local/reconcile", "/api/runtime/close/local"):
        status, payload = _invoke_local_close_api(monkeypatch, path)
        assert status.startswith("200")
        assert calls[-1][1] == {"cycle_id": "cycle-1", "external_id": "ticket-1"}
        if path.endswith("/reconcile"):
            assert payload["close_reconciliation"] == {"state": "OPEN", "read_only": True}
        else:
            assert payload["closed"] is True
            assert payload["close_state"] == "CLOSED"

    assert [item[0] for item in calls] == ["reconcile", "close"]


def test_local_ea_close_routes_still_reject_proxy_identity_and_non_loopback(monkeypatch):
    class CloseResult:
        accepted = True
        message = "closed"
        external_id = "ticket-1-close"

    monkeypatch.setattr(app_module.SERVICE, "close_mt5_position", lambda **kwargs: CloseResult())

    proxied_status, _ = _invoke_local_close_api(
        monkeypatch, "/api/runtime/close/local", access_identity="owner@example.com"
    )
    assert proxied_status.startswith("403")

    remote_status, _ = _invoke_local_close_api(
        monkeypatch, "/api/runtime/close/local", remote_addr="203.0.113.20"
    )
    assert remote_status.startswith("403")
