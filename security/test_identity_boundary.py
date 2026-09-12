import unittest

from security.identity_boundary import IdentityPolicy


class IdentityPolicyTests(unittest.TestCase):
    def test_production_identity_is_required_and_real_is_disabled(self):
        status = IdentityPolicy().status()
        self.assertEqual(status["production_identity"], "REQUIRED")
        self.assertEqual(status["trusted_identity_provider"], "NOT_CONFIGURED")
        self.assertEqual(status["tenant_isolation"], "DEPLOYMENT_BOUNDARY")
        self.assertEqual(status["real_execution"], "DISABLED")

    def test_production_authorization_fails_closed(self):
        policy = IdentityPolicy()
        self.assertFalse(policy.authorize_production_request(authenticated=False, tenant_id="tenant"))
        self.assertFalse(policy.authorize_production_request(authenticated=True, tenant_id=None))
        self.assertFalse(policy.authorize_production_request(authenticated=True, tenant_id="   "))
        self.assertTrue(policy.authorize_production_request(authenticated=True, tenant_id="tenant-1"))


if __name__ == "__main__":
    unittest.main()
