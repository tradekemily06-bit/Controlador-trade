import io
import json
import unittest

from app import application


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
            "/api/analyze",
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

    def test_ecosystem_image_round_trip_is_server_persisted(self):
        body = b"demo-image-bytes"
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/ecosystem-image",
            "QUERY_STRING": "kind=profile",
            "CONTENT_TYPE": "image/png",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
        response = b"".join(application(environ, start_response))
        self.assertEqual(captured["status"], "200 OK")
        self.assertTrue(json.loads(response)["saved"])

        captured = {}

        def start_response_get(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/ecosystem-image",
            "QUERY_STRING": "kind=profile",
            "CONTENT_TYPE": "",
            "CONTENT_LENGTH": "0",
            "wsgi.input": io.BytesIO(b""),
        }
        response = b"".join(application(environ, start_response_get))
        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(captured["headers"]["Content-Type"], "image/png")
        self.assertEqual(response, body)

    def test_index_mounts_existing_settings_media_component(self):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/",
            "QUERY_STRING": "",
            "wsgi.input": io.BytesIO(b""),
        }
        response = b"".join(application(environ, start_response)).decode("utf-8")
        self.assertEqual(captured["status"], "200 OK")
        self.assertIn('id="personalizacao-imagem"', response)
        self.assertIn('id="ecosystemImage"', response)
        self.assertIn("/api/ecosystem-image", response)


if __name__ == "__main__":
    unittest.main()
