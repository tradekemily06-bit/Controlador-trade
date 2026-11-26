from __future__ import annotations

import unittest

from security.identity_boundary import IdentityPolicy


class IdentityPolicyTests(unittest.TestCase):
    def test_status_does_not_claim_configured_identity_provider_or_tenant_isolation(self):
        status = IdentityPolicy().status()
        self.assertEqual(status["trusted_identity_provider"], "NOT_CONFIGURED")
        self.assertEqual(status["tenant_isolation"], "SINGLE_USER_RUNTIME_ONLY")
        self.assertEqual(status["multi_tenant_isolation"], "NOT_IMPLEMENTED")
        self.assertFalse(status["shared_bearer_token_is_user_identity"])
        self.assertEqual(status["real_execution"], "DISABLED")

    def test_remote_identity_requires_verified_authentication_and_nonempty_tenant(self):
        policy = IdentityPolicy()
        self.assertFalse(policy.authorize_production_request(authenticated=False, tenant_id="tenant-a"))
        self.assertFalse(policy.authorize_production_request(authenticated=True, tenant_id=None))
        self.assertFalse(policy.authorize_production_request(authenticated=True, tenant_id="  "))
        self.assertTrue(policy.authorize_production_request(authenticated=True, tenant_id="tenant-a"))


if __name__ == "__main__":
    unittest.main()
