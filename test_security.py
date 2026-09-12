import io
import unittest

from security_guard import MAX_BODY_BYTES, SecurityGuard


class SecurityGuardTests(unittest.TestCase):
    def test_rate_limit_blocks_after_threshold(self):
        guard = SecurityGuard(limit=2, window=60)
        env = {"REMOTE_ADDR": "10.0.0.1"}
        self.assertTrue(guard.allow(env, now=100))
        self.assertTrue(guard.allow(env, now=101))
        self.assertFalse(guard.allow(env, now=102))
        self.assertTrue(guard.allow(env, now=161))

    def test_clients_are_isolated(self):
        guard = SecurityGuard(limit=1, window=60)
        self.assertTrue(guard.allow({"REMOTE_ADDR": "10.0.0.1"}, now=100))
        self.assertTrue(guard.allow({"REMOTE_ADDR": "10.0.0.2"}, now=100))

    def test_security_headers_are_present(self):
        headers = dict(SecurityGuard.headers("abc123"))
        self.assertEqual(headers["X-Request-ID"], "abc123")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_body_limit_is_explicit(self):
        self.assertEqual(MAX_BODY_BYTES, 256 * 1024)


if __name__ == "__main__":
    unittest.main()
