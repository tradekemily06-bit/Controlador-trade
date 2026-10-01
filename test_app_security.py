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


if __name__ == "__main__":
    unittest.main()
