import pytest

from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus


def test_real_admission_accepts_only_strict_boolean_prerequisites():
    admission = RealAdmissionBoundary().admit(
        admission_id="adm",
        audit_id="audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="broker",
    )
    assert admission.status is RealAdmissionStatus.ADMITTED


@pytest.mark.parametrize(
    "field",
    ["audit_verified", "authorization_active", "safety_ready", "broker_available"],
)
def test_real_admission_rejects_non_boolean_prerequisite(field):
    values = {
        "audit_verified": True,
        "authorization_active": True,
        "safety_ready": True,
        "broker_available": True,
    }
    values[field] = 1
    with pytest.raises(TypeError):
        RealAdmissionBoundary().admit(
            admission_id="adm",
            audit_id="audit",
            broker_id="broker",
            **values,
        )


def test_real_admission_rejects_non_string_identity_fields():
    with pytest.raises(ValueError):
        RealAdmissionBoundary().admit(
            admission_id=None,
            audit_id="audit",
            audit_verified=True,
            authorization_active=True,
            safety_ready=True,
            broker_available=True,
            broker_id="broker",
        )
