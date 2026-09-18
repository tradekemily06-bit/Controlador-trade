import pytest

from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.real_authorization_issuer import RealAuthorizationIssuer


def _authorized_context():
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    auth = RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth", audit_id="audit",
        broker_id="broker", adapter_id="adapter", request_id="req", symbol="TEST",
        explicit_approval=True,
    )
    return audit, auth


def test_real_admission_accepts_only_boundary_issued_prerequisites():
    audit, auth = _authorized_context()
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=audit,
        authorization_active=auth, safety_ready=True, broker_available=True,
        broker_id="broker", adapter_id="adapter", request_id="req", symbol="TEST",
    )
    assert admission.status is RealAdmissionStatus.ADMITTED
    assert admission.admitted


@pytest.mark.parametrize("field", ["audit_verified", "authorization_active"])
def test_real_admission_rejects_boolean_claims_for_authority(field):
    audit, auth = _authorized_context()
    values = {"audit_verified": audit, "authorization_active": auth}
    values[field] = True
    with pytest.raises((TypeError, ValueError)):
        RealAdmissionBoundary().admit(
            admission_id="adm", audit_id="audit", safety_ready=True,
            broker_available=True, broker_id="broker", adapter_id="adapter",
            request_id="req", symbol="TEST", **values,
        )


@pytest.mark.parametrize("field", ["safety_ready", "broker_available"])
def test_real_admission_rejects_non_boolean_safety_prerequisites(field):
    audit, auth = _authorized_context()
    values = {"safety_ready": True, "broker_available": True}
    values[field] = 1
    with pytest.raises(TypeError):
        RealAdmissionBoundary().admit(
            admission_id="adm", audit_id="audit", audit_verified=audit,
            authorization_active=auth, broker_id="broker", adapter_id="adapter",
            request_id="req", symbol="TEST", **values,
        )


def test_real_admission_rejects_non_string_identity_fields():
    audit, auth = _authorized_context()
    with pytest.raises(ValueError):
        RealAdmissionBoundary().admit(
            admission_id=None, audit_id="audit", audit_verified=audit,
            authorization_active=auth, safety_ready=True, broker_available=True,
            broker_id="broker", adapter_id="adapter", request_id="req", symbol="TEST",
        )
