from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_invalid_tenant_is_rejected() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    event = SecurityEvent(1.0, "req", "GET", "/", 200, "hash")
    try:
        audit.record(tenant_id=" ", event=event)
    except ValueError:
        return
    raise AssertionError("tenant scope must be required")
