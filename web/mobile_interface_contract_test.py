from pathlib import Path


HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")


def test_mobile_viewport_and_pwa_contract():
    assert 'name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"' in HTML
    assert 'name="theme-color"' in HTML
    assert 'rel="manifest" href="/manifest.webmanifest"' in HTML
    assert 'mobile-web-app-capable' in HTML
    assert 'apple-mobile-web-app-capable' in HTML


def test_mobile_first_layout_contract():
    assert ".nav{position:fixed;bottom:0" in HTML
    assert ".app{max-width:1100px" in HTML
    assert ".grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in HTML
    assert "@media(min-width:720px)" in HTML
    assert "overflow-x:auto" in HTML


def test_mobile_operation_controls_remain_touch_friendly():
    assert ".btn{width:100%;" in HTML
    assert "padding:13px" in HTML
    assert ".controls input,.controls select" in HTML
    assert "padding:11px" in HTML
    assert ".nav a{font-size:11px" in HTML
    assert "white-space:nowrap" in HTML


def test_mobile_ui_keeps_real_execution_blocked():
    assert 'id="real"' in HTML and 'id="conexoes"' in HTML
    assert 'class="chip">REAL BLOQUEADO</span>' not in HTML
    assert "REAL /" not in HTML
    assert "Execução: DEMO" in HTML


def test_watermark_stays_subtle_and_does_not_cover_mobile_content():
    assert ".watermark-brand" in HTML
    assert "clamp(18px,3.8vw,42px)" in HTML
    assert "transform:rotate(-18deg)" not in HTML
    assert "watermark-mark" not in HTML
    assert "pointer-events:none" in HTML
    assert "opacity:.025" in HTML


def test_workspace_view_and_market_controls_sync_through_runtime():
    assert 'href="#painel">Cockpit</a>' in HTML
    assert 'id="grafico"' in HTML
    assert "workspace-hidden" in HTML
    assert "function applyWorkspacePreferences(p)" in HTML
    assert "function persistWorkspacePreferences()" in HTML
    assert "function persistDefaultView()" in HTML
    assert "$('refreshChart').onclick=refreshMarketChart;" in HTML
    assert "window.addEventListener('hashchange'" in HTML
    assert "default_view:view" in HTML
