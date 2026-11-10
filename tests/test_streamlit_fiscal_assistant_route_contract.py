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
