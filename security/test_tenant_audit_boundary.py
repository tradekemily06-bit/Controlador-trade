from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_snapshot_returns_copies() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    event = SecurityEvent(1.0, "req-1", "GET", "/api/health", 200, "hash")
    audit.record(tenant_id="tenant-a", event=event)
    first = audit.snapshot(tenant_id="tenant-a")
    first[0]["status"] = 500
    assert audit.snapshot(tenant_id="tenant-a")[0]["status"] == 200
