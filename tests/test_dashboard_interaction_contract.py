from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PANEL = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")


def test_dashboard_primary_controls_are_wired_to_click_or_change_handlers():
    # The circular C opens the ecosystem drawer; confirmation controls are
    # generated after successful API responses and bind inside their flows.
    required_bindings = (
        "const cToggle=$('ecosystemC'),ecosystemDrawer=$('ecosystemDrawer');" ,
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
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "ANALYZE",
        "CYCLE",
        "SAVE",
        "CLOSE",
    )
    assert "if(id!=CHARTEVENT_OBJECT_CLICK) return;" in handler
    for button in required_buttons:
        assert f'Obj("{button}")' in handler, f"MQL5 button has no click dispatch: {button}"


def test_compact_signal_shows_score_percent_and_level_only_for_actionable_quality():
    render = next(line for line in WEB.splitlines() if line.startswith("function render(d){"))
    assert "const actionable=q.actionable===true&&(isBuy||isSell);" in render
    assert "const signal=actionable?" in render
    assert "qs+'/100 · '+qs+'% '+ql" in render
    assert "if(actionable&&qs&&ql&&ql!=='NENHUMA')" in render


def test_compact_signal_does_not_promote_weak_or_unconfirmed_analysis():
    render = next(line for line in WEB.splitlines() if line.startswith("function render(d){"))
    assert "const signal=actionable?(isBuy?'COMPRAR':'VENDER'):'AGUARDAR';" in render
    assert "if(actionable&&qs&&ql&&ql!=='NENHUMA')" in render


def test_statistics_visually_separate_manual_study_from_confirmed_demo_financial_results():
    assert "ESTUDO — registros manuais (não representam lucro financeiro)" in WEB
    assert "DEMO — resultados financeiros confirmados pelo histórico MT5" in WEB
    for field in ("demoTotal", "demoWins", "demoLosses", "demoDraws", "demoWinrate", "demoNet"):
        assert f'id="{field}"' in WEB
    assert "st.demo||{}" in WEB
    assert "demo.periods?.daily" in WEB
    assert "demo.periods?.weekly" in WEB
    assert "demo.periods?.monthly" in WEB
    assert "MT5_DEMO_HISTORY" in WEB


def test_statistics_use_distinct_win_loss_colors_and_signed_net_result():
    assert ".stat-win{color:#58d68d}" in WEB
    assert ".stat-loss{color:#ff7676}" in WEB
    assert ".stat-neutral{color:#ffd166}" in WEB
    assert "n>0?'stat-win':Number(value)<0?'stat-loss':'stat-neutral'" in WEB


def test_statistics_do_not_report_zero_win_rate_when_no_closed_outcomes_exist():
    assert "!(Number(st.wins)+Number(st.losses))" in WEB
    assert "!(Number(data?.wins)+Number(data?.losses))" in WEB
    assert "!(Number(demo.wins)+Number(demo.losses))" in WEB
