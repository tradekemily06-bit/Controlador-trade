import io
import json
import unittest

from app import application


class ApiContractTests(unittest.TestCase):
    def request(self, path, method="GET", payload=None):
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
            "QUERY_STRING": "",
            "CONTENT_TYPE": "application/json" if payload is not None else "",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], json.loads(response)

    def test_read_endpoints_are_available_and_safe(self):
        for path in ("/api/health", "/api/status", "/api/memory", "/api/statistics", "/api/risk", "/api/news", "/api/connections"):
            status, headers, payload = self.request(path)
            self.assertEqual(status, "200 OK", path)
            self.assertIn("application/json", headers["Content-Type"])
            self.assertIsInstance(payload, dict)

        status, _, payload = self.request("/api/connections")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["real"], "DESABILITADO")
        self.assertEqual(payload["ic_markets_mt5_demo"], "DEMO_VALIDADO")

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
        status, headers, body = self._raw_request("/api/does-not-exist")
        self.assertEqual(status, "404 Not Found")
        self.assertIn("text/plain", headers["Content-Type"])
        self.assertEqual(body, b"Not Found")

    def _raw_request(self, path, method="GET"):
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
