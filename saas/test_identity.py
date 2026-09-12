from __future__ import annotations

import unittest

from saas.contracts import SaaSRole
from saas.identity import (
    IdentityBoundary,
    IdentityRequiredError,
    TrustedIdentity,
)


class StubIdentityProvider:
    def __init__(self, identity: TrustedIdentity | None) -> None:
        self.identity = identity

    def resolve_identity(self) -> TrustedIdentity | None:
        return self.identity


class IdentityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.boundary = IdentityBoundary()

    def test_resolves_trusted_identity_to_tenant_context(self) -> None:
        provider = StubIdentityProvider(
            TrustedIdentity("user-1", "tenant-a", SaaSRole.MEMBER)
        )
        context = self.boundary.resolve(provider)
        self.assertEqual(context.subject_id, "user-1")
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.role, SaaSRole.MEMBER)

    def test_missing_identity_fails_closed(self) -> None:
        with self.assertRaises(IdentityRequiredError):
            self.boundary.resolve(StubIdentityProvider(None))

    def test_blank_identity_fields_fail_closed(self) -> None:
        cases = [
            TrustedIdentity(" ", "tenant-a", SaaSRole.MEMBER),
            TrustedIdentity("user-1", " ", SaaSRole.MEMBER),
        ]
        for identity in cases:
            with self.subTest(identity=identity):
                with self.assertRaises(IdentityRequiredError):
                    self.boundary.resolve(StubIdentityProvider(identity))

    def test_invalid_role_fails_closed(self) -> None:
        identity = TrustedIdentity("user-1", "tenant-a", "member")  # type: ignore[arg-type]
        with self.assertRaises(IdentityRequiredError):
            self.boundary.resolve(StubIdentityProvider(identity))


if __name__ == "__main__":
    unittest.main()
