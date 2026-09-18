import pytest

from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary, RealAdmissionStatus


def _context(request_id="request", active=True):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit-1", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    auth = RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth-1", audit_id="audit-1",
        broker_id="broker", adapter_id="adapter", request_id=request_id,
        symbol="TEST", explicit_approval=True,
    )
    return audit, auth


def test_field_identical_fabricated_admission_is_not_admitted():
    audit, auth = _context()
    genuine = RealAdmissionBoundary().admit(
        admission_id="adm-1", audit_id="audit-1", audit_verified=audit,
        authorization_active=auth, safety_ready=True, broker_available=True,
        broker_id="broker", adapter_id="adapter", request_id="request", symbol="TEST",
    )
    fabricated = RealAdmission(
        genuine.admission_id, genuine.audit_id, genuine.status,
        genuine.broker_id, genuine.adapter_id, genuine.request_id,
        genuine.symbol, genuine.reasons,
    )
    assert genuine.status is RealAdmissionStatus.ADMITTED
    assert genuine.admitted
    assert fabricated == genuine
    assert fabricated is not genuine
    assert not fabricated.admitted


def test_boolean_claims_cannot_create_real_admission():
    audit, auth = _context()
    with pytest.raises((TypeError, ValueError)):
        RealAdmissionBoundary().admit(
            admission_id="adm-forged", audit_id="audit-1",
            audit_verified=True, authorization_active=True,
            safety_ready=True, broker_available=True,
            broker_id="broker", adapter_id="adapter",
            request_id="request", symbol="TEST",
        )


def test_blocked_admission_never_becomes_admitted():
    audit, auth = _context()
    blocked = RealAdmissionBoundary().admit(
        admission_id="adm-blocked", audit_id="audit-1",
        audit_verified=audit, authorization_active=auth,
        safety_ready=False, broker_available=True,
        broker_id="broker", adapter_id="adapter",
        request_id="request", symbol="TEST",
    )
    assert blocked.status is RealAdmissionStatus.BLOCKED
    assert not blocked.admitted
