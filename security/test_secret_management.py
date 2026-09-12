from __future__ import annotations

import unittest

from security.secret_management import SecretManagementBoundary, require_secret_manager


class TestOnlySecretManager(SecretManagementBoundary):
    production_ready = False

    def get_secret(self, name: str) -> str:
        raise RuntimeError("test-only manager must not expose production secrets")


class SecretManagementBoundaryTests(unittest.TestCase):
    def test_missing_manager_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_secret_manager(None)

    def test_unconfigured_manager_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_secret_manager(TestOnlySecretManager())

    def test_boundary_defaults_to_not_ready(self):
        manager = TestOnlySecretManager()
        self.assertFalse(manager.ready_for_production)


if __name__ == "__main__":
    unittest.main()
