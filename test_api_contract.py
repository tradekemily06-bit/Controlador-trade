import io
import json
import unittest

from app import application


class ApiContractTests(unittest.TestCase):
    def request(self, path, method="GET", payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "wsgi.url_scheme": "http",
            "wsgi.version": (1, 0),
            "wsgi.errors": io.StringIO(),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], json.loads(response)

    def test_read_endpoints_are_available_and_safe(self):
        for path in ("/api/health", "/api/status", "/api/saas/status", "/api/memory", "/api/statistics", "/api/risk", "/api/news", "/api/connections"):
            status, headers, payload = self.request(path)
            self.assertEqual(status, "200 OK")
            self.assertIsInstance(payload, dict)
            self.assertTrue(any(name.lower() == "x-request-id" for name, _ in headers))

    def test_saas_status_is_explicitly_provider_neutral_and_fail_closed(self):
        status, _, payload = self.request("/api/saas/status")
        self.assertEqual(status, "200 OK")
        self.assertTrue(payload["provider_neutral"])
        self.assertFalse(payload["real_execution"] == "ENABLED")

    def test_replay_accepts_more_than_the_removed_artificial_ceiling(self):
        status, _, payload = self.request(
            "/api/replay",
            method="POST",
            payload={"cases": [{} for _ in range(51)]},
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["results"]), 51)
        self.assertFalse(payload["execution_allowed"])

    def test_replay_rejects_non_list_cases(self):
        status, _, payload = self.request("/api/replay", method="POST", payload={"cases": {}})
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("error", payload)

    def test_outcome_updates_existing_decision(self):
        status, _, decision = self.request(
            "/api/analyze",
            method="POST",
            payload={"score": 90, "symbol": "EURUSD", "timeframe": "5m", "confirmed": True, "filters_ok": True},
        )
        self.assertEqual(status, "200 OK")

        status, _, updated = self.request(
            "/api/outcome",
            method="POST",
            payload={"decision_id": decision["decision_id"], "outcome": "WIN"},
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(updated["outcome"], "WIN")
