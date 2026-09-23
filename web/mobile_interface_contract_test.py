from pathlib import Path

HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
MANIFEST = Path(__file__).with_name("manifest.webmanifest").read_text(encoding="utf-8")


def test_mobile_viewport_and_pwa_contract():
    assert 'name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"' in HTML
    assert 'name="theme-color"' in HTML
    assert 'rel="manifest" href="/manifest.webmanifest"' in HTML
    assert 'mobile-web-app-capable' in HTML
    assert 'apple-mobile-web-app-capable' in HTML
    assert 'apple-touch-icon' in HTML
    assert 'rel="icon" href="/icons/icon.svg"' in HTML


def test_mobile_first_layout_contract():
    assert ".nav{position:fixed;bottom:0" in HTML
    assert ".app{width:100%;max-width:1100px" in HTML
    assert ".grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in HTML
    assert "@media(min-width:720px)" in HTML
    assert "@media(max-width:360px)" in HTML
    assert "@media(orientation:landscape)" in HTML
    assert "overflow-x:auto" in HTML
    assert "100dvh" in HTML


def test_mobile_operation_controls_remain_touch_friendly():
    assert ".btn{width:100%;min-height:44px;" in HTML
    assert "padding:13px" in HTML
    assert ".controls input,.controls select" in HTML
    assert "padding:11px" in HTML
    assert ".nav a{font-size:11px" in HTML
    assert "min-height:44px" in HTML
    assert "white-space:nowrap" in HTML


def test_mobile_ui_keeps_real_execution_blocked():
    assert "REAL BLOQUEADO" in HTML
    assert "REAL /" not in HTML
    assert "Execução: DEMO" in HTML


def test_pwa_manifest_is_device_neutral():
    assert '"display": "standalone"' in MANIFEST
    assert '"orientation": "any"' in MANIFEST
    assert '"scope": "/"' in MANIFEST
    assert '"/icons/icon.svg"' in MANIFEST


def test_device_adaptation_does_not_make_browser_storage_the_source_of_truth():
    assert "localStorage.setItem('ct_prefs'" not in HTML
    assert "getJson('/api/preferences')" in HTML
    assert "Preferências salvas no ecossistema" in HTML


def test_app_serves_the_pwa_icon_routes():
    app = Path(__file__).parents[1] / "app.py"
    source = app.read_text(encoding="utf-8")
    assert '"/icons/icon.svg"' in source
    assert '"/apple-touch-icon.svg"' in source


def test_mobile_inputs_avoid_small_text_zoom_and_support_accessibility():
    assert "font-size:16px" in HTML
    assert ".btn:focus-visible,.nav a:focus-visible" in HTML
    assert "prefers-reduced-motion:reduce" in HTML


def test_web_components_do_not_store_operational_state_in_browser_storage():
    components = Path(__file__).parent / "components"
    offenders = []
    for script in components.glob("*.js"):
        source = script.read_text(encoding="utf-8")
        if "localStorage" in source or "sessionStorage" in source or "indexedDB" in source:
            offenders.append(script.name)
    assert offenders == []


def test_onboarding_is_not_device_local_state():
    onboarding = (Path(__file__).parent / "components" / "onboarding.js").read_text(encoding="utf-8")
    assert "localStorage" not in onboarding
    assert "/api/onboarding" in onboarding

def test_ecosystem_image_persistence_uses_server_api_not_browser_storage():
    component = (Path(__file__).parent / "components" / "leverage-and-media.js").read_text(encoding="utf-8")
    assert "localStorage" not in component
    assert "sessionStorage" not in component
    assert "/api/ecosystem-image" in component
    assert "method:'POST'" in component
    assert "body:f" in component
