from __future__ import annotations

import unittest

from security.rate_limit import RateLimitStatus, require_centralized_rate_limiting


class RateLimitBoundaryTests(unittest.TestCase):
    def test_missing_status_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_centralized_rate_limiting(None)

    def test_incomplete_configuration_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_centralized_rate_limiting(RateLimitStatus(policy_configured=True))
        with self.assertRaises(RuntimeError):
            require_centralized_rate_limiting(RateLimitStatus(centralized_store_configured=True))

    def test_complete_configuration_is_ready(self):
        status = RateLimitStatus(
            centralized_store_configured=True,
            policy_configured=True,
        )
        self.assertTrue(status.ready_for_production)
        self.assertIs(require_centralized_rate_limiting(status), status)


if __name__ == "__main__":
    unittest.main()
