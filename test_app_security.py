import io
import json
import unittest

from app import application
from security_audit import MAX_SECURITY_PATH_LENGTH
from security_guard import MAX_BODY_BYTES


class AppSecurityTests(unittest.TestCase):
    def request(self, path, method="GET", payload=None, remote="test-client", trusted_identity=None, spoofed_identity=None):
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
        if trusted_identity:
            subject, tenant, role = trusted_identity
            environ["controlador.trusted_subject_id"] = subject
            environ["controlador.trusted_tenant_id"] = tenant
            environ["controlador.trusted_role"] = role
        if spoofed_identity:
            subject, tenant, role = spoofed_identity
            environ["HTTP_X_TRUSTED_SUBJECT_ID"] = subject
            environ["HTTP_X_TRUSTED_TENANT_ID"] = tenant
            environ["HTTP_X_TRUSTED_ROLE"] = role
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
        self.assertIn(b"Entrada invÃ¡lida", body)

    def test_oversized_path_is_bounded_in_audit_and_does_not_break_response(self):
        path = "/api/" + ("x" * (MAX_SECURITY_PATH_LENGTH + 500))
        status, _, _ = self.request(path)
        self.assertEqual(status, "404 Not Found")

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

    def test_public_saas_requires_server_trusted_identity(self, monkeypatch=None):
        import os
        old = os.environ.get("CONTROLADOR_SAAS_PUBLIC")
        os.environ["CONTROLADOR_SAAS_PUBLIC"] = "1"
        try:
            status, _, body = self.request("/api/memory")
            self.assertEqual(status, "403 Forbidden")
            self.assertIn(b"Acesso negado", body)
        finally:
            if old is None:
                os.environ.pop("CONTROLADOR_SAAS_PUBLIC", None)
            else:
                os.environ["CONTROLADOR_SAAS_PUBLIC"] = old

    def test_public_saas_ignores_browser_controlled_identity_headers(self):
        import os
        old = os.environ.get("CONTROLADOR_SAAS_PUBLIC")
        os.environ["CONTROLADOR_SAAS_PUBLIC"] = "1"
        try:
            status, _, body = self.request(
                "/api/memory",
                spoofed_identity=("attacker", "attacker-tenant", "admin"),
            )
            self.assertEqual(status, "403 Forbidden")
            self.assertIn(b"Acesso negado", body)
        finally:
            if old is None:
                os.environ.pop("CONTROLADOR_SAAS_PUBLIC", None)
            else:
                os.environ["CONTROLADOR_SAAS_PUBLIC"] = old

    def test_public_saas_owner_route_fails_closed_without_durable_provider(self):
        import os
        old_public = os.environ.get("CONTROLADOR_SAAS_PUBLIC")
        old_provider = os.environ.get("CONTROLADOR_PRODUCTION_STORE")
        os.environ["CONTROLADOR_SAAS_PUBLIC"] = "1"
        os.environ["CONTROLADOR_PRODUCTION_STORE"] = ""
        try:
            status, _, body = self.request(
                "/api/memory",
                trusted_identity=("user-1", "tenant-1", "user"),
            )
            self.assertEqual(status, "503 Service Unavailable")
            self.assertIn(b"SaaS", body)
        finally:
            if old_public is None:
                os.environ.pop("CONTROLADOR_SAAS_PUBLIC", None)
            else:
                os.environ["CONTROLADOR_SAAS_PUBLIC"] = old_public
            if old_provider is None:
                os.environ.pop("CONTROLADOR_PRODUCTION_STORE", None)
            else:
                os.environ["CONTROLADOR_PRODUCTION_STORE"] = old_provider


if __name__ == "__main__":
    unittest.main()
