from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_tenant_scope_is_required() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    event = SecurityEvent(1.0, "req", "GET", "/", 200, "hash")
    audit.record(tenant_id="tenant-a", event=event)
    assert audit.snapshot(tenant_id="tenant-a")[0]["request_id"] == "req"
