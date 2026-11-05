from pathlib import Path


def test_real_position_close_reconciliation_route_is_read_only():
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    route = source.split('if path == "/api/runtime/real/close/reconcile"', 1)[1].split(
        'if path == "/api/runtime/real/close"', 1
    )[0]
    assert "REAL_RUNTIME.reconcile_position_close" in route
    assert '"close_reconciliation": result' in route
    assert "REAL_RUNTIME.close_and_reconcile" not in route
