from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PANEL = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")


def test_dashboard_primary_controls_are_wired_to_click_or_change_handlers():
    # The MT5 toggle intentionally uses a local variable; all other primary
    # static controls bind directly by ID. The two confirmation/close controls
    # are generated after a successful API response and bind inside their flows.
    required_bindings = (
        "const mt5Toggle=$('mt5PanelToggle'),mt5Panel=$('mt5SidePanel');mt5Toggle.onclick=",
        "$('refreshChart').onclick=refreshMarketChart",
        "$('saveOperationMode').onclick=async()",
        "$('realPrepare').onclick=async()",
        "$('realConfirm').onclick=async()",
        "$('runtimeCycle').onclick=runRuntimeCycle",
        "$('analyze').onclick=async()",
        "$('replayBtn').onclick=async()",
        "$('savePrefs').onclick=async()",
        "$('symbolInput').addEventListener('change'",
        "$('tfInput').addEventListener('change'",
        "window.addEventListener('hashchange',()=>applyDefaultView",
    )
    for binding in required_bindings:
        assert binding in WEB, f"Dashboard control lost its interaction binding: {binding}"


def test_dashboard_navigation_targets_are_supported_and_react_to_hash_changes():
    nav_targets = ("painel", "analise", "memoria", "laboratorio", "noticias", "config")
    for target in nav_targets:
        assert f'href="#{target}"' in WEB, f"Missing navigation target: {target}"

    allowed_views = "const allowed=new Set(['painel','analise','laboratorio','memoria','noticias','config'])"
    assert allowed_views in WEB
    assert "function applyDefaultView(view)" in WEB
    assert "window.addEventListener('hashchange',()=>applyDefaultView" in WEB


def test_dashboard_actions_have_matching_runtime_api_routes():
    required_routes = (
        "/api/preferences",
        "/api/runtime/real/status",
        "/api/runtime/real/prepare",
        "/api/runtime/real/confirm",
        "/api/runtime/cycle",
        "/api/runtime/close",
        "/api/runtime/analysis",
        "/api/market/assets",
        "/api/replay",
        "/api/risk",
        "/api/statistics",
        "/api/memory",
        "/api/news",
        "/api/outcome",
        "/api/status",
    )
    for route in required_routes:
        assert f'"{route}"' in APP, f"Dashboard route is missing from app.py: {route}"


def test_mql5_visible_buttons_dispatch_chart_click_events():
    click_start = PANEL.index("void OnChartEvent(")
    handler = PANEL[click_start:]
    handler = handler.split("\n}\n", 1)[0]

    required_buttons = (
        "PANEL_TOGGLE",
        "N1",
        "N2",
        "N3",
        "N4",
        "N5",
        "N6",
        "N7",
        "N8",
        "N9",
        "ANALYZE",
        "CYCLE",
        "SAVE",
        "CLOSE",
        "WM",
    )
    assert "if(id!=CHARTEVENT_OBJECT_CLICK) return;" in handler
    for button in required_buttons:
        assert f'Obj("{button}")' in handler, f"MQL5 button has no click dispatch: {button}"
