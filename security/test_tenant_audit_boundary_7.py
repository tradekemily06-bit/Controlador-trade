from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary


def test_missing_scope_fails_closed() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    try:
        audit.snapshot(tenant_id=None)  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("missing tenant scope must fail closed")
