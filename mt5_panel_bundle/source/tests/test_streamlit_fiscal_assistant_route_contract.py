from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PANEL_SOURCE = (ROOT / "streamlit_panel" / "app.py").read_text(encoding="utf-8")
API_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _panel_uses(path: str) -> bool:
    # Query strings and per-record suffixes are intentionally normalized to
    # their stable route prefix before checking the backend contract.
    return path in PANEL_SOURCE


def _backend_registers(path: str) -> bool:
    exact = re.search(rf'path\s*==\s*["\']{re.escape(path)}["\']', API_SOURCE)
    prefix = re.search(rf'path\.startswith\(["\']{re.escape(path)}["\']\)', API_SOURCE)
    return bool(exact or prefix)


def test_assistant_panel_actions_have_backend_routes():
    routes = {
        "/api/assistant/status",
        "/api/assistant/test-connection",
        "/api/assistant/conversations",
        "/api/assistant/history",
        "/api/assistant/chat",
    }
    for route in routes:
        assert _panel_uses(route), f"Streamlit no longer uses assistant route {route}"
        assert _backend_registers(route), f"Backend route missing for assistant action {route}"


def test_fiscal_panel_actions_have_backend_routes():
    routes = {
        "/api/fiscal-reserve",
        "/api/fiscal-reserve/rates",
        "/api/fiscal-reserve/results",
        "/api/fiscal-reserve/domestic-pending",
        "/api/fiscal-reserve/domestic-pending/summary",
        "/api/fiscal-reserve/pending",
        "/api/fiscal-reserve/pending-result",
        "/api/fiscal-reserve/mt5-preview",
        "/api/fiscal-reserve/mt5-confirm",
        "/api/fiscal-reserve/mt5-pending-result",
    }
    for route in routes:
        assert _panel_uses(route), f"Streamlit no longer uses fiscal route {route}"
        assert _backend_registers(route), f"Backend route missing for fiscal action {route}"


def test_review_routes_are_owner_scoped_backend_subresources():
    assert '"/api/fiscal-reserve/domestic-pending/"' in PANEL_SOURCE
    assert '"/api/fiscal-reserve/pending/"' in PANEL_SOURCE
    assert 'path.startswith("/api/fiscal-reserve/domestic-pending/")' in API_SOURCE
    assert 'path.startswith("/api/fiscal-reserve/pending/")' in API_SOURCE


def test_financeiro_overview_is_read_only_and_does_not_duplicate_fiscal_writes():
    start = PANEL_SOURCE.index("def show_finance_overview()")
    end = PANEL_SOURCE.index("\ndef _kill_switch_activation_payload", start)
    overview = PANEL_SOURCE[start:end]
    assert 'api("/api/fiscal-reserve?limit=50&offset=0")' in overview
    assert 'api("/api/fiscal-reserve/domestic-pending/summary")' in overview
    assert 'method="POST"' not in overview
    assert "st.form_submit_button" not in overview


def _registered_backend_route(route: str) -> bool:
    normalized = route.split("?", 1)[0]
    normalized = re.sub(r"\{[^}]+\}", "", normalized)
    candidates = [normalized]
    candidate = normalized.rstrip("/")
    while candidate and candidate != "/api":
        candidates.append(candidate)
        candidate = candidate.rsplit("/", 1)[0]
    for candidate in dict.fromkeys(candidates):
        escaped = re.escape(candidate)
        if re.search(rf'path\s*==\s*["\']{escaped}["\']', API_SOURCE):
            return True
        if re.search(rf'path\.startswith\(["\']{escaped}["\']\)', API_SOURCE):
            return True
    return False


def test_every_literal_streamlit_api_call_has_a_backend_route():
    # Cover every Streamlit surface, not only the fiscal and assistant pages.
    # Query strings and formatted per-record suffixes are normalized first.
    routes = {
        match.group(2).split("?", 1)[0]
        for match in re.finditer(r'api\(\s*(?:f)?(["\'])(/api/[^"\'\x60]+)\1', PANEL_SOURCE)
    }
    assert len(routes) >= 40, "API route inventory unexpectedly shrank; review panel changes"
    missing = sorted(route for route in routes if not _registered_backend_route(route))
    assert not missing, f"Streamlit calls have no backend route: {missing}"


def _literal_panel_api_method_calls():
    import ast

    tree = ast.parse(PANEL_SOURCE)
    calls = set()

    def literal_route_prefix(expression):
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            return expression.value.split("?", 1)[0]
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
            return literal_route_prefix(expression.left)
        if isinstance(expression, ast.JoinedStr):
            for part in expression.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str) and part.value:
                    return part.value.split("?", 1)[0]
                if isinstance(part, ast.FormattedValue):
                    break
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "api":
            continue
        if not node.args:
            continue
        route = literal_route_prefix(node.args[0])
        if not route or not route.startswith("/api/"):
            continue
        method = "GET"
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            method = node.args[1].value.upper()
        for keyword in node.keywords:
            if keyword.arg == "method" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                method = keyword.value.value.upper()
        calls.add((route, method))
    return calls


def _backend_registers_method(route: str, method: str) -> bool:
    import ast

    tree = ast.parse(API_SOURCE)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        conditions = node.test.values if isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.And) else [node.test]
        path_matches = any(
            isinstance(condition, ast.Compare)
            and isinstance(condition.left, ast.Name)
            and condition.left.id == "path"
            and len(condition.ops) == 1
            and isinstance(condition.ops[0], ast.Eq)
            and len(condition.comparators) == 1
            and isinstance(condition.comparators[0], ast.Constant)
            and condition.comparators[0].value == route
            for condition in conditions
        )
        method_matches = any(
            isinstance(condition, ast.Compare)
            and isinstance(condition.left, ast.Name)
            and condition.left.id == "method"
            and len(condition.ops) == 1
            and isinstance(condition.ops[0], ast.Eq)
            and len(condition.comparators) == 1
            and isinstance(condition.comparators[0], ast.Constant)
            and condition.comparators[0].value == method
            for condition in conditions
        )
        if path_matches and method_matches:
            return True
    return False


def test_high_risk_assistant_and_fiscal_panel_actions_use_registered_http_methods():
    # Route existence alone is insufficient: a GET/POST/DELETE mismatch can
    # leave a visible button broken or accidentally expose a write operation.
    expected = {
        ("/api/assistant/status", "GET"),
        ("/api/assistant/test-connection", "POST"),
        ("/api/assistant/conversations", "GET"),
        ("/api/assistant/conversations", "DELETE"),
        ("/api/assistant/history", "GET"),
        ("/api/assistant/chat", "POST"),
        ("/api/fiscal-reserve", "GET"),
        ("/api/fiscal-reserve/rates", "POST"),
        ("/api/fiscal-reserve/results", "POST"),
        ("/api/fiscal-reserve/domestic-pending", "GET"),
        ("/api/fiscal-reserve/domestic-pending", "POST"),
        ("/api/fiscal-reserve/domestic-pending/summary", "GET"),
        ("/api/fiscal-reserve/pending", "GET"),
        ("/api/fiscal-reserve/pending", "POST"),
        ("/api/fiscal-reserve/pending-result", "POST"),
        ("/api/fiscal-reserve/mt5-preview", "GET"),
        ("/api/fiscal-reserve/mt5-confirm", "POST"),
        ("/api/fiscal-reserve/mt5-pending-result", "POST"),
    }
    panel_calls = _literal_panel_api_method_calls()
    missing_from_panel = sorted(expected - panel_calls)
    assert not missing_from_panel, f"Critical panel actions are missing or use the wrong HTTP method: {missing_from_panel}"
    missing_from_backend = sorted(
        (route, method)
        for route, method in expected
        if not _backend_registers_method(route, method)
    )
    assert not missing_from_backend, f"Backend handlers are missing for critical method contracts: {missing_from_backend}"
