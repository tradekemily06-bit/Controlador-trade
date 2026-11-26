from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from standalone_app import StandaloneWSGIApplication


class FakeRuntime:
    closed = False

    class Application:
        def architecture(self):
            return {
                "architecture": "ONE_SHARED_INTELLIGENCE",
                "application_areas": [{"name": str(i)} for i in range(7)],
                "area_handler_status": {},
            }

        def handle(self, *, area, task, context=None):
            return {
                "area": area,
                "task": task,
                "status": "NOT_CONNECTED",
                "execution_authorized": False,
            }

    application = Application()

    class EcosystemService:
        def notification_items(self, *, include_info=False):
            return [{"notification_id": "n1", "title": "Sinal atualizado"}]

        def notification_summary(self):
            return {"total": 1, "external_delivery": "OUTBOX_ONLY_NO_PROVIDER"}

    ecosystem_service = EcosystemService()
    notification_worker = None


def call_wsgi(app, path, method="GET", body=None, remote_addr="127.0.0.1", origin=None, include_headers=False, authorization=None, identity_verified=False, remote_user=None, tenant_id=None):
    raw = json.dumps(body or {}).encode("utf-8")
    parsed_path = urlsplit(path)
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": parsed_path.path,
        "QUERY_STRING": parsed_path.query,
        "REMOTE_ADDR": remote_addr,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    if origin is not None:
        environ["HTTP_ORIGIN"] = origin
    if authorization is not None:
        environ["HTTP_AUTHORIZATION"] = authorization
    if identity_verified:
        environ["controlador.identity_verified"] = True
    if remote_user is not None:
        environ["REMOTE_USER"] = remote_user
    if tenant_id is not None:
        environ["controlador.tenant_id"] = tenant_id
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    response = b"".join(app(environ, start_response))
    decoded = json.loads(response.decode("utf-8")) if response else {}
    result = (captured["status"], decoded)
    return (*result, captured["headers"]) if include_headers else result


class StandaloneWSGITests(unittest.TestCase):
    def test_health_exposes_one_intelligence_and_seven_areas(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/health")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["architecture"], "ONE_SHARED_INTELLIGENCE")
        self.assertEqual(body["areas"], 7)
        self.assertFalse(body["execution_authorized"])

    def test_readiness_endpoint_reports_unconfigured_services_without_claiming_live(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/readiness")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["areas"], 7)
        self.assertEqual(body["market_data"]["status"], "NOT_CONFIGURED")
        self.assertEqual(body["news"]["status"], "NOT_CONFIGURED")
        self.assertEqual(body["notification_delivery"]["state"], "NO_EXTERNAL_SINK_CONFIGURED")
        self.assertEqual(body["deployment"], "PROCESS_RUNNING_DEPLOYMENT_NOT_VERIFIED")
        self.assertEqual(body["identity"]["trusted_identity_provider"], "NOT_CONFIGURED")
        self.assertEqual(body["identity"]["multi_tenant_isolation"], "NOT_IMPLEMENTED")
        self.assertFalse(body["identity"]["shared_bearer_token_is_user_identity"])
        self.assertFalse(body["execution_authorized"])

    def test_timeframe_catalog_exposes_supported_intervals_and_limits(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/market-data/timeframes")
        self.assertEqual(status, "200 OK")
        self.assertIn("1m", body["canonical"])
        self.assertIn("10m", body["canonical"])
        self.assertIn("M1", body["platform"])
        self.assertIn("M10", body["platform"])
        self.assertIn("M59", body["platform"])
        self.assertIn("H24", body["platform"])
        self.assertIn("D31", body["platform"])
        self.assertIn("W4", body["platform"])
        self.assertNotIn("MN1", body["platform"])
        self.assertIn("months", body["excluded"])
        self.assertEqual(body["parser_support"], "NORMALIZATION_ONLY")
        self.assertEqual(body["provider_compatibility"]["status"], "NO_PROVIDER_SELECTED")
        self.assertFalse(body["execution_authorized"])

    def test_architecture_endpoint_is_read_only(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/intelligence/architecture")
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(body["application_areas"]), 7)

    def test_unknown_order_endpoint_does_not_exist(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/orders", method="POST", body={"symbol": "EURUSD"})
        self.assertEqual(status, "404 Not Found")
        self.assertFalse(body["execution_authorized"])

    def test_notifications_endpoint_returns_persisted_inbox(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/notifications?limit=10")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["notifications"][0]["notification_id"], "n1")
        self.assertFalse(body["execution_authorized"])

    def test_notification_status_reports_no_external_sink_honestly(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/notifications/status")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["external_delivery"], "OUTBOX_ONLY_NO_PROVIDER")
        self.assertFalse(body["delivery_worker"]["configured"])

    def test_notifications_endpoint_rejects_invalid_limit(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/notifications?limit=999")
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])

    def test_cors_allows_only_explicitly_configured_frontend_origin(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_ALLOWED_ORIGINS": "https://app.example.com"}):
            status, body, headers = call_wsgi(
                app, "/api/health", origin="https://app.example.com",
                include_headers=True,
            )
            self.assertEqual(status, "200 OK")
            self.assertIn(
                ("Access-Control-Allow-Origin", "https://app.example.com"),
                headers,
            )
            denied_status, denied_body = call_wsgi(
                app, "/api/health", origin="https://attacker.example"
            )
            self.assertEqual(denied_status, "403 Forbidden")
            self.assertFalse(denied_body["execution_authorized"])

    def test_cors_preflight_supports_frontend_api_methods(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_ALLOWED_ORIGINS": "https://app.example.com"}):
            status, _ = call_wsgi(
                app, "/api/market-monitor/subscriptions",
                method="OPTIONS", origin="https://app.example.com",
            )
        self.assertEqual(status, "204 No Content")


    def test_shared_bearer_token_alone_does_not_authenticate_remote_user(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/health", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn("identidade remota verificada", body["error"])
        self.assertFalse(body["execution_authorized"])

    def test_remote_access_requires_verified_subject_and_tenant(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/health", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="user-123", tenant_id="tenant-abc",
            )
        self.assertEqual(status, "200 OK")
        self.assertFalse(body["execution_authorized"])

    def test_remote_access_is_denied_by_default(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/health", remote_addr="203.0.113.10")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertFalse(body["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
