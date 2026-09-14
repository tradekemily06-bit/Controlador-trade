from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "components" / "onboarding.html").read_text(encoding="utf-8")
JS = (ROOT / "web" / "components" / "onboarding.js").read_text(encoding="utf-8")


def test_onboarding_component_is_separate_and_hidden_by_default():
    assert 'id="onboardingCenter"' in HTML
    assert 'class="card onboarding-center hidden"' in HTML
    assert 'id="onboardingClose"' in HTML


def test_onboarding_uses_read_only_guide_api_and_preserves_execution_boundary():
    assert '/api/onboarding' in JS
    assert 'guide.execution_authorized !== false' in JS
    for forbidden in ('/api/analyze', '/api/outcome', 'COMPRA', 'VENDA'):
        assert forbidden not in JS


def test_server_mounts_onboarding_with_existing_csp_nonce():
    assert 'WEB_DIR / "components" / "onboarding.html"' in APP
    assert 'WEB_DIR / "components" / "onboarding.js"' in APP
    assert 'onboarding_script = f\'<script nonce="{script_nonce}">{onboarding_js}</script>\'' in APP
    assert 'notification_mount + onboarding_mount + anchor' in APP
