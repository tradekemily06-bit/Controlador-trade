from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_snapshot_is_copy() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    audit.record(tenant_id="tenant-a", event=SecurityEvent(1.0, "req", "GET", "/", 200, "hash"))
    data = audit.snapshot(tenant_id="tenant-a")
    data[0]["status"] = 500
    assert audit.snapshot(tenant_id="tenant-a")[0]["status"] == 200
