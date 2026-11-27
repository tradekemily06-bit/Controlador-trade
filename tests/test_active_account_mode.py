from __future__ import annotations

import unittest

from core.active_account_mode import resolve_active_account_mode


class DemoAdapter:
    def get_account_mode(self):
        return "demo"


class RealAdapter:
    def get_account_mode(self):
        return "REAL"


class InvalidAdapter:
    def get_account_mode(self):
        return "DEMO / REAL"


class BrokenAdapter:
    def get_account_mode(self):
        raise RuntimeError("connection lost")


class ActiveAccountModeTests(unittest.TestCase):
    def test_demo_returns_only_demo(self):
        self.assertEqual(resolve_active_account_mode(DemoAdapter())["mode"], "DEMO")

    def test_real_returns_only_real(self):
        self.assertEqual(resolve_active_account_mode(RealAdapter())["mode"], "REAL")

    def test_missing_adapter_is_unavailable(self):
        result = resolve_active_account_mode(None)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["mode"])

    def test_invalid_combined_mode_is_rejected(self):
        result = resolve_active_account_mode(InvalidAdapter())
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["mode"])

    def test_connection_error_fails_closed(self):
        result = resolve_active_account_mode(BrokenAdapter())
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["mode"])


if __name__ == "__main__":
    unittest.main()
