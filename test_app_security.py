import io
import json
import os
import unittest
from unittest.mock import patch

from app import application
from security_guard import MAX_BODY_BYTES


class AppSecurityTests(unittest.TestCase):
    def request(self, path, method="GET", payload=None, remote="test-client", scheme="http", forwarded_proto=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
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
            "REMOTE_ADDR": remote,
            "wsgi.input": io.BytesIO(body),
            "wsgi.url_scheme": scheme,
        }
        if forwarded_proto is not None:
            environ["HTTP_X_FORWARDED_PROTO"] = forwarded_proto
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], response

    def test_security_headers_and_request_id_are_returned(self):
        status, headers, _ = self.request("/api/health")
        self.assertEqual(status, "200 OK")
        self.assertTrue(headers["X-Request-ID"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_production_https_requirement_blocks_plain_http(self):
        with patch.dict(os.environ, {"CONTROLADOR_REQUIRE_HTTPS": "1", "CONTROLADOR_TRUSTED_PROXY_CIDRS": ""}, clear=False):
            status, _, body = self.request("/api/health", scheme="http")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"transporte seguro", body)

    def test_production_https_allows_direct_tls_and_adds_hsts(self):
        with patch.dict(os.environ, {"CONTROLADOR_REQUIRE_HTTPS": "1", "CONTROLADOR_TRUSTED_PROXY_CIDRS": ""}, clear=False):
            status, headers, _ = self.request("/api/health", scheme="https")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Strict-Transport-Security"], "max-age=63072000; includeSubDomains")

    def test_production_forwarded_https_requires_trusted_proxy(self):
        with patch.dict(os.environ, {"CONTROLADOR_REQUIRE_HTTPS": "1", "CONTROLADOR_TRUSTED_PROXY_CIDRS": "192.0.2.0/24"}, clear=False):
            status, headers, _ = self.request("/api/health", remote="192.0.2.10", scheme="http", forwarded_proto="https")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Strict-Transport-Security"], "max-age=63072000; includeSubDomains")

    def test_oversized_json_is_rejected(self):
        payload = {"value": "x" * (MAX_BODY_BYTES + 1)}
        status, _, body = self.request("/api/analyze", method="POST", payload=payload)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn(b"Entrada inv\xc3\xa1lida", body)

    def test_rate_limit_is_per_client(self):
        from app import SECURITY
        old_limit = SECURITY.limit
        try:
            SECURITY.limit = 1
            first, _, _ = self.request("/api/health", remote="client-a")
            blocked, _, _ = self.request("/api/health", remote="client-a")
            other, _, _ = self.request("/api/health", remote="client-b")
            self.assertEqual(first, "200 OK")
            self.assertEqual(blocked, "429 Too Many Requests")
            self.assertEqual(other, "200 OK")
        finally:
            SECURITY.limit = old_limit
            SECURITY._buckets.clear()


if __name__ == "__main__":
    unittest.main()
