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
    assert "REAL BLOQUEADO" in HTML
    assert "REAL /" not in HTML
    assert "Execução: DEMO" in HTML
