from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary


def test_invalid_event_fails_closed() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    try:
        audit.record(tenant_id="tenant-a", event=None)  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("invalid audit event must fail closed")
