import io
import json
import unittest

from app import SERVICE, application


class WebInterfaceSmokeTests(unittest.TestCase):
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
        return captured["status"], captured["headers"], response

    def test_dashboard_serves_html(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers.get("Content-Type", ""))
        html = body.decode("utf-8")
        for marker in (
            "Controlador Trading",
            'id="painel"',
            'id="analise"',
            'id="laboratorio"',
            'id="memoria"',
            'id="risco"',
            'id="conexoes"',
            "/api/market/analyze",
            "/api/replay",
        ):
            self.assertIn(marker, html)

    def test_status_is_demo_safe(self):
        status, _, body = self.request("/api/status")
        self.assertEqual(status, "200 OK")
        data = json.loads(body)
        self.assertEqual(data["mode"], "SIMULACAO")
        self.assertFalse(data["execution_allowed"])
        self.assertEqual(data["mt5_demo"], "DEMO_VALIDADO")
        self.assertEqual(data["real"], "DESABILITADO")

    def test_analyze_endpoint_returns_decision(self):
        status, _, body = self.request(
            "/api/analyze",
            method="POST",
            payload={
                "score": 85,
                "symbol": "EURUSD",
                "timeframe": "5m",
                "confirmed": True,
                "filters_ok": True,
            },
        )
        self.assertEqual(status, "200 OK")
        data = json.loads(body)
        self.assertIn(data["signal"], {"COMPRA", "VENDA", "AGUARDAR"})
        self.assertEqual(data["symbol"], "EURUSD")
        self.assertEqual(data["timeframe"], "5m")


    def test_kill_switch_endpoint_is_fail_closed(self):
        status, _, body = self.request("/api/kill-switch")
        self.assertEqual(status, "200 OK")
        data = json.loads(body)
        self.assertFalse(data["execution_allowed"])
        status, _, body = self.request(
            "/api/kill-switch",
            method="POST",
            payload={"action": "activate", "reason": "teste de interface"},
        )
        self.assertEqual(status, "200 OK")
        data = json.loads(body)
        self.assertTrue(data["enabled"])
        self.assertFalse(data["execution_allowed"])
        self.assertTrue(SERVICE.operational_runtime.kill_switch.state.enabled)
        SERVICE.operational_runtime.kill_switch.deactivate()

    def test_dashboard_mounts_shared_runtime_controls(self):
        status, _, body = self.request("/")
        self.assertEqual(status, "200 OK")
        html = body.decode("utf-8")
        self.assertIn("kill-switch-control", html)
        self.assertIn("personalizacao-imagem", html)

    def test_pwa_icon_is_served_by_backend(self):
        status, headers, body = self.request("/icons/icon.svg")
        self.assertEqual(status, "200 OK")
        self.assertIn("image/svg+xml", headers.get("Content-Type", ""))
        self.assertIn(b"<svg", body)

    def test_leverage_assessment_is_risk_only(self):
        status, _, body = self.request(
            "/api/leverage/assess",
            method="POST",
            payload={
                "request_id": "ui-test",
                "profile_id": "p1",
                "symbol": "EURUSD",
                "requested_leverage": 2,
                "capital_allocated": 1000,
                "quantity": 1,
                "price": 100,
                "stop_distance": 1,
                "value_per_price_unit": 1,
                "maximum_loss": 100,
            },
        )
        self.assertEqual(status, "200 OK")
        data = json.loads(body)
        self.assertFalse(data["execution_authorized"])

if __name__ == "__main__":
    unittest.main()
