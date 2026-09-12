from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_invalid_event_is_rejected() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    try:
        audit.record(tenant_id="tenant-a", event=object())  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("invalid audit event must be rejected")
