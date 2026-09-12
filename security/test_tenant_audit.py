from __future__ import annotations

import unittest

from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


class TenantAuditBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = TenantAuditBoundary(InMemoryTenantAuditSink())
        self.event = SecurityEvent(
            timestamp=1.0,
            request_id="req-1",
            method="GET",
            path="/api/health",
            status=200,
            client_hash="hashed",
        )

    def test_records_are_isolated_by_tenant(self) -> None:
        self.audit.record(tenant_id="tenant-a", event=self.event)
        self.audit.record(tenant_id="tenant-b", event=self.event)
        self.assertEqual(len(self.audit.snapshot(tenant_id="tenant-a")), 1)
        self.assertEqual(len(self.audit.snapshot(tenant_id="tenant-b")), 1)
        self.assertEqual(self.audit.snapshot(tenant_id="tenant-c"), [])

    def test_missing_tenant_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.audit.record(tenant_id=" ", event=self.event)
        with self.assertRaises(ValueError):
            self.audit.snapshot(tenant_id="")
        with self.assertRaises(ValueError):
            self.audit.snapshot(tenant_id=None)  # type: ignore[arg-type]

    def test_event_type_is_validated(self) -> None:
        with self.assertRaises(TypeError):
            self.audit.record(tenant_id="tenant-a", event=object())  # type: ignore[arg-type]

    def test_snapshot_is_a_copy(self) -> None:
        self.audit.record(tenant_id="tenant-a", event=self.event)
        snapshot = self.audit.snapshot(tenant_id="tenant-a")
        snapshot[0]["status"] = 500
        self.assertEqual(self.audit.snapshot(tenant_id="tenant-a")[0]["status"], 200)


if __name__ == "__main__":
    unittest.main()
