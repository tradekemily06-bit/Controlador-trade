from pathlib import Path


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
