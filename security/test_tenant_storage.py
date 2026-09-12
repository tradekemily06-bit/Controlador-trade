from __future__ import annotations

import unittest

from security.tenant_context import TenantContext
from security.tenant_storage import TenantStorageBoundary, require_tenant_context


class MemoryProbeStorage(TenantStorageBoundary):
    """Test-only implementation; explicitly not production durable."""

    production_durable = False

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], object] = {}

    def get(self, context: TenantContext, key: str):
        context = require_tenant_context(context)
        return self.values.get((context.tenant_id, key))

    def put(self, context: TenantContext, key: str, value: object) -> None:
        context = require_tenant_context(context)
        self.values[(context.tenant_id, key)] = value

    def delete(self, context: TenantContext, key: str) -> None:
        context = require_tenant_context(context)
        self.values.pop((context.tenant_id, key), None)


class TenantStorageBoundaryTests(unittest.TestCase):
    def test_missing_context_fails_closed(self):
        with self.assertRaises(PermissionError):
            require_tenant_context(None)

    def test_storage_is_tenant_scoped(self):
        storage = MemoryProbeStorage()
        tenant_a = TenantContext("tenant-a", "user-a")
        tenant_b = TenantContext("tenant-b", "user-b")
        storage.put(tenant_a, "setting", "A")
        storage.put(tenant_b, "setting", "B")
        self.assertEqual(storage.get(tenant_a, "setting"), "A")
        self.assertEqual(storage.get(tenant_b, "setting"), "B")

    def test_local_probe_never_claims_production_durability(self):
        self.assertFalse(MemoryProbeStorage().ready_for_production)


if __name__ == "__main__":
    unittest.main()
