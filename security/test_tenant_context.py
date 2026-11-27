from __future__ import annotations

import unittest

from security.tenant_context import TenantContext, build_trusted_tenant_context


class TenantContextTests(unittest.TestCase):
    def test_requires_non_empty_ids(self):
        with self.assertRaises(ValueError):
            TenantContext("", "subject")
        with self.assertRaises(ValueError):
            TenantContext("tenant", "   ")

    def test_builder_fails_closed_without_trusted_authentication(self):
        self.assertIsNone(
            build_trusted_tenant_context(
                authenticated=False, tenant_id="tenant", subject_id="subject"
            )
        )
        self.assertIsNone(
            build_trusted_tenant_context(
                authenticated=True, tenant_id=None, subject_id="subject"
            )
        )
        self.assertIsNone(
            build_trusted_tenant_context(
                authenticated=True, tenant_id="tenant", subject_id=None
            )
        )

    def test_key_encoding_is_unambiguous_for_delimiter_characters(self):
        left = TenantContext("a:subject:b", "c")
        right = TenantContext("a", "b:subject:c")
        self.assertNotEqual(left.key, right.key)

    def test_builder_returns_canonical_immutable_context(self):
        context = build_trusted_tenant_context(
            authenticated=True, tenant_id=" tenant-1 ", subject_id=" user-1 "
        )
        self.assertEqual(context.tenant_id, "tenant-1")
        self.assertEqual(context.subject_id, "user-1")
        self.assertEqual(context.key, "tenant:8:tenant-1:subject:6:user-1")
        with self.assertRaises((AttributeError, TypeError)):
            context.tenant_id = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
