from pathlib import Path


def test_real_position_close_reconciliation_route_is_read_only():
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    route = source.split('if path == "/api/runtime/real/close/reconcile"', 1)[1].split(
        'if path == "/api/runtime/real/close"', 1
    )[0]
    assert "REAL_RUNTIME.reconcile_position_close" in route
    assert '"close_reconciliation": result' in route
    assert "REAL_RUNTIME.close_and_reconcile" not in route


def test_real_position_close_reconciliation_route_does_not_coerce_input_types():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    route_start = source.index('if path == "/api/runtime/real/close/reconcile" and method == "POST":')
    route_end = source.index('if path == "/api/runtime/real/close" and method == "POST":', route_start)
    route = source[route_start:route_end]

    assert "request_id=data.get(\"request_id\")" in route
    assert "external_id=data.get(\"external_id\")" in route
    assert 'request_id=str(data.get' not in route
    assert 'external_id=str(data.get' not in route
