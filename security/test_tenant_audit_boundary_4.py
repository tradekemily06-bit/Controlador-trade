from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_other_tenant_cannot_see_events() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    event = SecurityEvent(1.0, "req", "GET", "/", 200, "hash")
    audit.record(tenant_id="tenant-a", event=event)
    assert audit.snapshot(tenant_id="tenant-b") == []
