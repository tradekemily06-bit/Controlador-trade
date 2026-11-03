import io
import json
import os
import unittest

from app import application
from security_guard import MAX_BODY_BYTES


class AppSecurityTests(unittest.TestCase):
    def request(self, path, method="GET", payload=None, remote="test-client", headers=None):
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
        }
        for key, value in (headers or {}).items():
            environ[key] = value
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], response

    def test_security_headers_and_request_id_are_returned(self):
        status, headers, _ = self.request("/api/health")
        self.assertEqual(status, "200 OK")
        self.assertTrue(headers["X-Request-ID"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_oversized_json_is_rejected(self):
        payload = {"value": "x" * (MAX_BODY_BYTES + 1)}
        status, _, body = self.request("/api/analyze", method="POST", payload=payload)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn(b"Entrada inv\xc3\xa1lida", body)


    def test_local_health_probe_is_not_throttled(self):
        from app import SECURITY
        old_limit = SECURITY.limit
        try:
            SECURITY.limit = 1
            for _ in range(5):
                status, _, _ = self.request("/api/health", remote="127.0.0.1")
                self.assertEqual(status, "200 OK")
        finally:
            SECURITY.limit = old_limit
            SECURITY._buckets.clear()

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

    def test_explicit_local_notebook_mutation_requires_local_host(self):
        from app import _authorize_remote_mutation
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "true"
            os.environ["CONTROLADOR_LOCAL_MUTATION_HOSTS"] = "localhost,127.0.0.1"
            local_allowed, _ = _authorize_remote_mutation(
                {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "localhost:8000"}
            )
            public_host_denied, _ = _authorize_remote_mutation(
                {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "controlador.example.com"}
            )
            remote_denied, _ = _authorize_remote_mutation(
                {"REMOTE_ADDR": "10.0.0.25", "HTTP_HOST": "controlador.example.com"}
            )
            self.assertTrue(local_allowed)
            self.assertFalse(public_host_denied)
            self.assertFalse(remote_denied)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_remote_access_requires_trusted_identity_when_enabled(self):
        from app import _authorize_remote_mutation
        old_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED")
        old_header = os.environ.get("CONTROLADOR_TRUSTED_IDENTITY_HEADER")
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            allowed, _ = _authorize_remote_mutation({"REMOTE_ADDR": "127.0.0.1", "HTTP_X_AUTHENTICATED_USER": "user@example.com"})
            denied, _ = _authorize_remote_mutation({"REMOTE_ADDR": "127.0.0.1"})
            self.assertTrue(allowed)
            self.assertFalse(denied)
        finally:
            if old_required is None:
                os.environ.pop("CONTROLADOR_REMOTE_ACCESS_REQUIRED", None)
            else:
                os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = old_required
            if old_header is None:
                os.environ.pop("CONTROLADOR_TRUSTED_IDENTITY_HEADER", None)
            else:
                os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = old_header


    def test_assistant_conversation_reads_require_trusted_identity_remotely(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            denied, _, denied_body = self.request(
                "/api/assistant/conversations", remote="203.0.113.20"
            )
            allowed, _, allowed_body = self.request(
                "/api/assistant/conversations",
                remote="203.0.113.20",
                headers={"HTTP_X_AUTHENTICATED_USER": "audit-user@example.com"},
            )
            self.assertEqual(denied, "401 Unauthorized")
            self.assertIn("Identidade autenticada necessária".encode(), denied_body)
            self.assertEqual(allowed, "200 OK")
            self.assertIn(b'"conversations"', allowed_body)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


    def test_all_remote_assistant_routes_require_trusted_identity(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            routes = [
                ("/api/assistant/conversations", "GET", None),
                ("/api/assistant/history?conversation_id=not-owned", "GET", None),
                ("/api/assistant/chat", "POST", {"message": "teste"}),
            ]
            for path, method, payload in routes:
                status, _, body = self.request(path, method=method, payload=payload, remote="203.0.113.44")
                self.assertEqual(status, "401 Unauthorized", path)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_remote_fiscal_and_assistant_delete_routes_require_identity(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            routes = [
                ("/api/fiscal-reserve", "GET", None),
                ("/api/fiscal-reserve/mt5-preview", "GET", None),
                ("/api/fiscal-reserve/pending", "GET", None),
                ("/api/fiscal-reserve/pending", "POST", {"reference": "REMOTE-UNAUTH", "original_amount": 1, "original_currency": "USD", "instrument": "ETF", "jurisdiction": "US", "occurred_on": "2026-11-02"}),
                ("/api/fiscal-reserve/rates", "POST", {"category": "BR_DAY_TRADE", "rate": 20}),
                ("/api/fiscal-reserve/results", "POST", {"category": "BR_DAY_TRADE", "realized_result_brl": 10, "reference": "REMOTE-UNAUTH"}),
                ("/api/assistant/conversations", "DELETE", None),
            ]
            expected = [
                "403 Forbidden", "403 Forbidden", "403 Forbidden",
                "401 Unauthorized", "401 Unauthorized", "401 Unauthorized",
                "401 Unauthorized",
            ]
            for (path, method, payload), expected_status in zip(routes, expected):
                status, _, _ = self.request(
                    path, method=method, payload=payload, remote="203.0.113.77"
                )
                self.assertEqual(status, expected_status, f"{method} {path}")
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

if __name__ == "__main__":
    unittest.main()
