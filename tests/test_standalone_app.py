from __future__ import annotations

import io
import json
import unittest

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


def call_wsgi(app, path, method="GET", body=None, remote_addr="127.0.0.1"):
    raw = json.dumps(body or {}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "REMOTE_ADDR": remote_addr,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    response = b"".join(app(environ, start_response))
    return captured["status"], json.loads(response.decode("utf-8"))


class StandaloneWSGITests(unittest.TestCase):
    def test_health_exposes_one_intelligence_and_seven_areas(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/health")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["architecture"], "ONE_SHARED_INTELLIGENCE")
        self.assertEqual(body["areas"], 7)
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

    def test_remote_access_is_denied_by_default(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/health", remote_addr="203.0.113.10")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertFalse(body["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
