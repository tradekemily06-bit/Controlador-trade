from __future__ import annotations

import unittest

from security.durable_audit import DurableAuditBoundary, require_durable_audit
from security.tenant_context import TenantContext


class MemoryAuditProbe(DurableAuditBoundary):
    production_durable = False

    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, object]]] = {}

    def record(self, context: TenantContext, event: dict[str, object]) -> None:
        self.events.setdefault(context.tenant_id, []).append(dict(event))

    def snapshot(self, context: TenantContext) -> list[dict[str, object]]:
        return [dict(event) for event in self.events.get(context.tenant_id, [])]


class DurableAuditBoundaryTests(unittest.TestCase):
    def test_missing_boundary_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_durable_audit(None)

    def test_local_probe_is_not_production_ready(self):
        with self.assertRaises(RuntimeError):
            require_durable_audit(MemoryAuditProbe())

    def test_tenant_scope_is_preserved(self):
        audit = MemoryAuditProbe()
        tenant_a = TenantContext("tenant-a", "user-a")
        tenant_b = TenantContext("tenant-b", "user-b")
        audit.record(tenant_a, {"action": "A"})
        audit.record(tenant_b, {"action": "B"})
        self.assertEqual(audit.snapshot(tenant_a), [{"action": "A"}])
        self.assertEqual(audit.snapshot(tenant_b), [{"action": "B"}])


if __name__ == "__main__":
    unittest.main()
