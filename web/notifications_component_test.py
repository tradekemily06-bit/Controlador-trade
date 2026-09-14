from pathlib import Path


COMPONENT_DIR = Path(__file__).with_name("components")
HTML = (COMPONENT_DIR / "notifications.html").read_text(encoding="utf-8")
JS = (COMPONENT_DIR / "notifications.js").read_text(encoding="utf-8")


def test_notification_component_keeps_critical_and_important_visible_without_info_noise():
    assert 'id="notificationCritical"' in HTML
    assert 'id="notificationImportant"' in HTML
    assert 'id="notificationInfo"' in HTML
    assert 'class="list hidden"' in HTML
    assert "CRITICAL" in JS
    assert "IMPORTANT" in JS


def test_notification_component_uses_summary_then_expands_full_list_on_demand():
    assert "fetch('/api/notifications')" in JS
    assert "fetch('/api/notifications/all')" in JS
    assert "VER TODAS" in JS
    assert "OCULTAR INFORMATIVAS" in JS
    assert "infoBox.classList.remove('hidden')" in JS
    assert "/api/updates" not in JS


def test_notification_component_has_no_execution_controls_or_authority():
    for forbidden in ("/api/analyze", "/api/outcome", "execution", "COMPRA", "VENDA"):
        assert forbidden not in JS
    assert "window.ControladorNotifications" in JS
