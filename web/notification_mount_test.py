from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
COMPONENT_HTML = (ROOT / "web" / "components" / "notifications.html").read_text(encoding="utf-8")
COMPONENT_JS = (ROOT / "web" / "components" / "notifications.js").read_text(encoding="utf-8")


def test_index_keeps_single_operational_cockpit_and_mount_anchor():
    assert '<section class="hero" id="painel">' in INDEX
    assert '<div class="section">Visão geral</div>' in INDEX
    assert 'id="notificationCenter"' not in INDEX


def test_server_mounts_reusable_notification_component_into_index_only():
    assert 'path == WEB_DIR / "index.html"' in APP
    assert 'WEB_DIR / "components" / "notifications.html"' in APP
    assert 'WEB_DIR / "components" / "notifications.js"' in APP
    assert 'anchor = \'<div class="section">Visão geral</div>\'.encode("utf-8")' in APP
    assert 'script nonce="{script_nonce}"' in APP


def test_mount_remains_read_only_and_non_authorizing():
    assert "/api/notifications" in COMPONENT_JS
    for forbidden in ("/api/analyze", "/api/outcome", "COMPRA", "VENDA"):
        assert forbidden not in COMPONENT_JS
    assert "execution_authorized" not in COMPONENT_HTML
