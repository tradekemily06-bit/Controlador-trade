from __future__ import annotations

import unittest

from security.wsgi_identity import trusted_tenant_context_from_wsgi


class TrustedWSGIIdentityTests(unittest.TestCase):
    def test_requires_explicit_middleware_enablement(self):
        environ = {
            "controlador.identity_verified": True,
            "controlador.tenant_id": "tenant-a",
            "controlador.subject_id": "user-a",
        }
        self.assertIsNone(
            trusted_tenant_context_from_wsgi(environ, middleware_enabled=False)
        )

    def test_accepts_only_server_injected_verified_identity(self):
        environ = {
            "controlador.identity_verified": True,
            "controlador.tenant_id": "tenant-a",
            "controlador.subject_id": "user-a",
            "HTTP_X_TENANT_ID": "attacker-tenant",
            "HTTP_X_USER_ID": "attacker-user",
        }
        context = trusted_tenant_context_from_wsgi(
            environ, middleware_enabled=True
        )
        self.assertIsNotNone(context)
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.subject_id, "user-a")

    def test_rejects_unverified_or_incomplete_identity(self):
        base = {
            "controlador.tenant_id": "tenant-a",
            "controlador.subject_id": "user-a",
        }
        self.assertIsNone(
            trusted_tenant_context_from_wsgi(
                {**base, "controlador.identity_verified": False},
                middleware_enabled=True,
            )
        )
        self.assertIsNone(
            trusted_tenant_context_from_wsgi(
                {"controlador.identity_verified": True, "controlador.tenant_id": "tenant-a"},
                middleware_enabled=True,
            )
        )
        self.assertIsNone(
            trusted_tenant_context_from_wsgi(
                {"controlador.identity_verified": True, "controlador.subject_id": "user-a"},
                middleware_enabled=True,
            )
        )

    def test_rejects_blank_claims(self):
        self.assertIsNone(
            trusted_tenant_context_from_wsgi(
                {
                    "controlador.identity_verified": True,
                    "controlador.tenant_id": " ",
                    "controlador.subject_id": "user-a",
                },
                middleware_enabled=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
