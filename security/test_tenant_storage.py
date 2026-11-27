from __future__ import annotations

import unittest
from types import SimpleNamespace

from security.tenant_context import TenantContext
from security.tenant_storage import TenantStorageBoundary, require_tenant_context


class MemoryProbeStorage(TenantStorageBoundary):
    """Test-only implementation; explicitly not production durable."""

    production_durable = False

    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], object] = {}

    def get(self, context: TenantContext, key: str):
        context = require_tenant_context(context)
        return self.values.get((context.tenant_id, context.subject_id, key))

    def put(self, context: TenantContext, key: str, value: object) -> None:
        context = require_tenant_context(context)
        self.values[(context.tenant_id, context.subject_id, key)] = value

    def delete(self, context: TenantContext, key: str) -> None:
        context = require_tenant_context(context)
        self.values.pop((context.tenant_id, context.subject_id, key), None)


class TenantStorageBoundaryTests(unittest.TestCase):
    def test_missing_context_fails_closed(self):
        with self.assertRaises(PermissionError):
            require_tenant_context(None)

    def test_non_context_objects_fail_closed(self):
        for value in ("tenant-a", {}, SimpleNamespace(tenant_id="a", subject_id="b")):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                require_tenant_context(value)

    def test_mutated_noncanonical_context_fails_closed(self):
        context = TenantContext("tenant-a", "user-a")
        object.__setattr__(context, "tenant_id", " tenant-a")
        with self.assertRaisesRegex(PermissionError, "canonical tenant context"):
            require_tenant_context(context)

    def test_storage_is_scoped_by_tenant_and_subject(self):
        storage = MemoryProbeStorage()
        tenant_a_user_a = TenantContext("tenant-a", "user-a")
        tenant_a_user_b = TenantContext("tenant-a", "user-b")
        tenant_b_user_a = TenantContext("tenant-b", "user-a")
        storage.put(tenant_a_user_a, "setting", "A")
        storage.put(tenant_a_user_b, "setting", "B")
        storage.put(tenant_b_user_a, "setting", "C")
        self.assertEqual(storage.get(tenant_a_user_a, "setting"), "A")
        self.assertEqual(storage.get(tenant_a_user_b, "setting"), "B")
        self.assertEqual(storage.get(tenant_b_user_a, "setting"), "C")

    def test_local_probe_never_claims_production_durability(self):
        self.assertFalse(MemoryProbeStorage().ready_for_production)


if __name__ == "__main__":
    unittest.main()
