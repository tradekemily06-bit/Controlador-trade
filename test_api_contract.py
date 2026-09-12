import io
import json
import unittest

from app import application


class ApiContractTests(unittest.TestCase):
    def request(self, path, method="GET", payload=None, query=""):
        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/json" if payload is not None else "",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], json.loads(response)

    def test_read_endpoints_are_available_and_safe(self):
        for path in ("/api/health", "/api/status", "/api/saas/status", "/api/memory", "/api/statistics", "/api/risk", "/api/news", "/api/connections"):
            status, headers, payload = self.request(path)
            self.assertEqual(status, "200 OK", path)
            self.assertIn("application/json", headers["Content-Type"])
            self.assertIsInstance(payload, dict)

        status, _, payload = self.request("/api/connections")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["real"], "DESABILITADO")
        self.assertEqual(payload["ic_markets_mt5_demo"], "DEMO_VALIDADO")
        self.assertEqual(payload["saas"], "FOUNDATION")

    def test_saas_status_is_explicitly_provider_neutral_and_fail_closed(self):
        status, _, payload = self.request("/api/saas/status")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["runtime"], "FOUNDATION")
        self.assertTrue(payload["provider_neutral"])
        self.assertFalse(payload["paid_dependency_required"])
        self.assertEqual(payload["tenant_scoped_access"], "BOUNDARY_READY")
        self.assertEqual(payload["authentication_provider"], "NOT_CONFIGURED")
        self.assertEqual(payload["billing"], "OUTSIDE_CORE")
        self.assertEqual(payload["dashboard_onboarding"], "NOT_CONFIGURED")
        self.assertEqual(payload["real_execution"], "DISABLED")
        self.assertEqual(payload["identity"]["real_execution"], "DISABLED")

    def test_web_manifest_is_served(self):
        status, headers, payload = self.request_raw("/manifest.webmanifest")
        self.assertEqual(status, "200 OK")
        self.assertIn("application/manifest+json", headers["Content-Type"])
        manifest = json.loads(payload)
        self.assertEqual(manifest["name"], "Controlador Trading")
        self.assertEqual(manifest["display"], "standalone")

    def test_query_limits_are_parsed_and_hardened(self):
        status, _, payload = self.request("/api/memory", query="limit=1")
        self.assertEqual(status, "200 OK")
        self.assertLessEqual(len(payload["records"]), 1)

        status, _, payload = self.request("/api/news", query="limit=abc")
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("error", payload)

        status, _, payload = self.request("/api/memory", query="limit=0")
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("error", payload)

    def test_analyze_exposes_stable_presentation_and_security_contract(self):
        status, _, payload = self.request(
            "/api/analyze",
            method="POST",
            payload={"score": 90, "symbol": "EURUSD", "timeframe": "5m", "confirmed": True, "filters_ok": True},
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["signal"], "COMPRA")
        self.assertEqual(payload["presentation"]["status"], "BUY")
        self.assertEqual(payload["presentation"]["label"], "COMPRA")
        self.assertEqual(payload["presentation"]["color"], "green")
        self.assertTrue(payload["security"]["real_blocked"])
        self.assertTrue(payload["execution_allowed"] is False)
        self.assertIn("decision_id", payload)

    def test_replay_records_multiple_cases(self):
        status, _, payload = self.request(
            "/api/replay",
            method="POST",
            payload={"cases": [
                {"score": 90, "symbol": "EURUSD", "timeframe": "5m", "confirmed": True, "filters_ok": True},
                {"score": 20, "symbol": "EURUSD", "timeframe": "5m", "confirmed": False, "filters_ok": True},
            ]},
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["results"]), 2)
        self.assertFalse(payload["execution_allowed"])

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
        self.assertEqual(updated["decision_id"], decision["decision_id"])
        self.assertEqual(updated["outcome"], "WIN")

    def test_invalid_replay_payload_fails_closed(self):
        status, _, payload = self.request("/api/replay", method="POST", payload={"cases": "invalid"})
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("error", payload)

    def test_unknown_route_is_not_found(self):
        status, headers, body = self.request_raw("/api/does-not-exist")
        self.assertEqual(status, "404 Not Found")
        self.assertIn("text/plain", headers["Content-Type"])
        self.assertEqual(body, b"Not Found")

    def request_raw(self, path, method="GET"):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_TYPE": "",
            "CONTENT_LENGTH": "0",
            "wsgi.input": io.BytesIO(b""),
        }
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], response


if __name__ == "__main__":
    unittest.main()
