from __future__ import annotations

import unittest

from security.input_validation import InputValidationError, validate_json_value
from security.local_auth import LocalAuth


class LocalAuthTests(unittest.TestCase):
    def test_password_hash_is_not_plaintext_and_verifies(self):
        encoded = LocalAuth.hash_password("A-strong-password-123!")
        self.assertNotIn("A-strong-password-123!", encoded)
        self.assertTrue(LocalAuth.verify_password("A-strong-password-123!", encoded))
        self.assertFalse(LocalAuth.verify_password("wrong-password-123!", encoded))

    def test_short_password_is_rejected(self):
        with self.assertRaises(ValueError):
            LocalAuth.hash_password("short")


class InputValidationTests(unittest.TestCase):
    def test_non_finite_values_are_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_json_value(float("nan"))

    def test_deep_json_is_rejected(self):
        value = {}
        current = value
        for _ in range(13):
            current["x"] = {}
            current = current["x"]
        with self.assertRaises(InputValidationError):
            validate_json_value(value)


if __name__ == "__main__":
    unittest.main()
