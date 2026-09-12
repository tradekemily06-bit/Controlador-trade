from __future__ import annotations

from security.tenant_audit import InMemoryTenantAuditSink, TenantAuditBoundary
from security_audit import SecurityEvent


def test_tenant_audit_isolation_and_fail_closed_scope() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    event = SecurityEvent(1.0, "req-1", "GET", "/api/health", 200, "hashed")
    audit.record(tenant_id="tenant-a", event=event)
    audit.record(tenant_id="tenant-b", event=event)
    assert len(audit.snapshot(tenant_id="tenant-a")) == 1
    assert len(audit.snapshot(tenant_id="tenant-b")) == 1

    try:
        audit.snapshot(tenant_id="")
    except ValueError:
        pass
    else:
        raise AssertionError("missing tenant must fail closed")


def test_tenant_audit_rejects_invalid_event() -> None:
    audit = TenantAuditBoundary(InMemoryTenantAuditSink())
    try:
        audit.record(tenant_id="tenant-a", event=object())  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("invalid audit events must be rejected")
