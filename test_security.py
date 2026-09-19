import io
import os
import unittest

from security_guard import MAX_BODY_BYTES, MAX_TRACKED_CLIENTS, SecurityGuard


class SecurityGuardTests(unittest.TestCase):
    def test_rate_limit_blocks_after_threshold(self):
        guard = SecurityGuard(limit=2, window=60)
        env = {"REMOTE_ADDR": "10.0.0.1"}
        self.assertTrue(guard.allow(env, now=100))
        self.assertTrue(guard.allow(env, now=101))
        self.assertFalse(guard.allow(env, now=102))
        self.assertTrue(guard.allow(env, now=161))

    def test_non_loopback_requires_explicit_bearer_token(self):
        guard = SecurityGuard()
        env = {"REMOTE_ADDR": "10.0.0.1"}
        old = os.environ.pop("CONTROLADOR_API_TOKEN", None)
        try:
            self.assertFalse(guard.authorize(env))
            os.environ["CONTROLADOR_API_TOKEN"] = "secret-token"
            self.assertFalse(guard.authorize(env))
            env["HTTP_AUTHORIZATION"] = "Bearer wrong"
            self.assertFalse(guard.authorize(env))
            env["HTTP_AUTHORIZATION"] = "Bearer secret-token"
            self.assertTrue(guard.authorize(env))
        finally:
            if old is None:
                os.environ.pop("CONTROLADOR_API_TOKEN", None)
            else:
                os.environ["CONTROLADOR_API_TOKEN"] = old

    def test_loopback_does_not_require_remote_token(self):
        guard = SecurityGuard()
        self.assertTrue(guard.authorize({"REMOTE_ADDR": "127.0.0.1"}))
        self.assertTrue(guard.authorize({"REMOTE_ADDR": "::1"}))

    def test_clients_are_isolated(self):
        guard = SecurityGuard(limit=1, window=60)
        self.assertTrue(guard.allow({"REMOTE_ADDR": "10.0.0.1"}, now=100))
        self.assertTrue(guard.allow({"REMOTE_ADDR": "10.0.0.2"}, now=100))

    def test_stale_client_buckets_are_pruned(self):
        guard = SecurityGuard(limit=1, window=60)
        guard.allow({"REMOTE_ADDR": "10.0.0.1"}, now=100)
        guard.allow({"REMOTE_ADDR": "10.0.0.2"}, now=100)
        guard.allow({"REMOTE_ADDR": "10.0.0.3"}, now=161)
        self.assertEqual(set(guard._buckets), {"10.0.0.3"})

    def test_tracked_clients_are_bounded(self):
        guard = SecurityGuard(limit=1, window=60)
        for index in range(MAX_TRACKED_CLIENTS + 25):
            self.assertTrue(guard.allow({"REMOTE_ADDR": f"10.0.{index // 256}.{index % 256}"}, now=100))
        self.assertLessEqual(len(guard._buckets), MAX_TRACKED_CLIENTS)

    def test_invalid_rate_limit_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            SecurityGuard(limit=0)
        with self.assertRaises(ValueError):
            SecurityGuard(window=0)

    def test_script_nonce_is_random_and_usable(self):
        guard = SecurityGuard()
        first = guard.script_nonce()
        second = guard.script_nonce()
        self.assertTrue(first)
        self.assertNotEqual(first, second)
        headers = dict(SecurityGuard.headers("abc123", script_nonce=first))
        csp = headers["Content-Security-Policy"]
        self.assertIn(f"'nonce-{first}'", csp)
        self.assertIn("script-src 'self'", csp)

    def test_security_headers_without_nonce_remain_strict(self):
        headers = dict(SecurityGuard.headers("abc123"))
        csp = headers["Content-Security-Policy"]
        self.assertEqual(headers["X-Request-ID"], "abc123")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_body_limit_is_explicit(self):
        self.assertEqual(MAX_BODY_BYTES, 256 * 1024)


if __name__ == "__main__":
    unittest.main()
