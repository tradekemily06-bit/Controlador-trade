import io
import json
import os
import unittest
from unittest.mock import patch

from app import application
from security.http_identity import resolve_trusted_identity, require_role, require_trusted_identity


class HttpIdentityTests(unittest.TestCase):
    def test_browser_headers_are_not_treated_as_trusted_identity(self):
        environ = {
            "HTTP_X_SUBJECT_ID": "attacker",
            "HTTP_X_TENANT_ID": "attacker-tenant",
            "HTTP_X_ROLE": "admin",
        }
        self.assertIsNone(resolve_trusted_identity(environ))

    def test_trusted_wsgi_identity_requires_all_fields(self):
        environ = {
            "controlador.trusted_subject_id": "user-1",
            "controlador.trusted_tenant_id": "tenant-1",
            "controlador.trusted_role": "user",
        }
        identity = require_trusted_identity(environ)
        self.assertEqual(identity.subject_id, "user-1")
        self.assertEqual(identity.tenant_id, "tenant-1")
        self.assertEqual(identity.role, "user")

    def test_admin_role_is_explicit(self):
        environ = {
            "controlador.trusted_subject_id": "user-1",
            "controlador.trusted_tenant_id": "tenant-1",
            "controlador.trusted_role": "user",
        }
        identity = require_trusted_identity(environ)
        with self.assertRaises(PermissionError):
            require_role(identity, "admin")

    def request(self, payload=None, trusted=False, role="user"):
        body = json.dumps(payload or {}).encode("utf-8")
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/analyze",
            "QUERY_STRING": "",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
        if trusted:
            environ.update({
                "controlador.trusted_subject_id": "user-1",
                "controlador.trusted_tenant_id": "tenant-1",
                "controlador.trusted_role": role,
            })
        with patch.dict(os.environ, {"CONTROLADOR_SAAS_PUBLIC": "true"}, clear=False):
            response = b"".join(application(environ, start_response))
        return captured["status"], json.loads(response)

    def test_public_saas_mutation_fails_closed_without_identity(self):
        status, payload = self.request({"score": 90})
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("request_id", payload)

    def test_public_saas_mutation_fails_closed_until_tenant_storage_exists(self):
        status, payload = self.request(
            {"score": 90, "symbol": "EURUSD", "timeframe": "5m", "confirmed": True, "filters_ok": True},
            trusted=True,
        )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(payload["error"], "Serviço SaaS indisponível até que o armazenamento seguro esteja configurado.")


if __name__ == "__main__":
    unittest.main()
