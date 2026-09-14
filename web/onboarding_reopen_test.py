from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "web" / "components" / "onboarding.js").read_text(encoding="utf-8")


def test_reopen_control_lives_inside_existing_settings_area():
    assert 'document.getElementById("config")' in JS
    assert 'nextElementSibling' in JS
    assert 'onboardingReopenControl' in JS
    assert 'ABRIR MODO DE USAR' in JS


def test_reopen_uses_the_read_only_guide_and_never_adds_execution_authority():
    assert 'refresh(true)' in JS
    assert 'guide.execution_authorized !== false' in JS
    for forbidden in ('/api/analyze', '/api/outcome', 'COMPRA', 'VENDA'):
        assert forbidden not in JS
