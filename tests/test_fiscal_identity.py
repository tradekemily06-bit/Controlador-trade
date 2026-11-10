import os
import unittest
from unittest.mock import patch

from finance.fiscal_identity import (
    FiscalOwnerIdentityError,
    configured_fiscal_owner_id,
)


class FiscalOwnerIdentityTests(unittest.TestCase):
    def test_missing_identity_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FiscalOwnerIdentityError):
                configured_fiscal_owner_id()

    def test_identity_is_normalized_and_opaque(self):
        with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": " Owner@Example.com "}):
            first = configured_fiscal_owner_id()
        with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": "owner@example.COM"}):
            second = configured_fiscal_owner_id()
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("single:"))
        self.assertNotIn("owner@example.com", first)

    def test_different_configured_identity_has_different_owner(self):
        with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": "one@example.com"}):
            first = configured_fiscal_owner_id()
        with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": "two@example.com"}):
            second = configured_fiscal_owner_id()
        self.assertNotEqual(first, second)


    def test_malformed_identity_fails_closed_at_owner_resolution_boundary(self):
        malformed_values = (
            "x" * 321,
            "owner@example.com\r\nX-Injected: yes",
            "owner@example.com\x00",
            "owner@example.com\x7f",
        )
        for value in malformed_values:
            with self.subTest(value=repr(value)):
                with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": value}):
                    with self.assertRaises(FiscalOwnerIdentityError):
                        configured_fiscal_owner_id()

    def test_identity_trims_whitespace_before_enforcing_limit(self):
        with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": " " + "x" * 320 + " "}):
            owner_id = configured_fiscal_owner_id()
        self.assertTrue(owner_id.startswith("single:"))

    def test_identity_limit_is_checked_after_trimming(self):
        with patch.dict(os.environ, {"CONTROLADOR_SINGLE_USER_IDENTITY": " " + "x" * 321 + " "}):
            with self.assertRaises(FiscalOwnerIdentityError):
                configured_fiscal_owner_id()


if __name__ == "__main__":
    unittest.main()
