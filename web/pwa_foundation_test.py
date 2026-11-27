import json
from pathlib import Path


WEB = Path(__file__).parent


def test_pwa_manifest_has_installable_identity_and_icon():
    manifest = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Controlador Trading"
    assert manifest["short_name"] == "Controlador"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["icons"]
    assert any(
        icon["src"] == "/pwa/icon.svg"
        and icon["type"] == "image/svg+xml"
        and icon["purpose"] == "any maskable"
        for icon in manifest["icons"]
    )


def test_service_worker_never_caches_authenticated_or_market_data():
    worker = (WEB / "service-worker.js").read_text(encoding="utf-8")
    assert 'url.pathname.startsWith("/api/")' in worker
    assert 'request.mode === "navigate"' in worker
    assert "if (url.href !== PUBLIC_ICON) return;" in worker
    assert "caches.open(CACHE_NAME)" in worker
    assert 'self.addEventListener("push"' in worker
    assert 'self.addEventListener("notificationclick"' in worker


def test_registration_requires_secure_context_and_does_not_request_permission():
    registration = (WEB / "pwa-registration.js").read_text(encoding="utf-8")
    assert 'window.isSecureContext === true' in registration
    assert 'navigator.serviceWorker.register("/service-worker.js"' in registration
    assert "Notification.requestPermission" not in registration
    assert "pushManager.subscribe" not in registration


def test_pwa_icon_is_a_valid_vector_asset():
    icon = (WEB / "pwa" / "icon.svg").read_text(encoding="utf-8")
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in icon
    assert 'viewBox="0 0 512 512"' in icon
