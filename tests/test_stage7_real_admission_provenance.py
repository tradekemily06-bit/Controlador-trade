from core.p117_real_admission import RealAdmission, RealAdmissionBoundary, RealAdmissionStatus


def test_field_identical_fabricated_admission_is_not_admitted():
    genuine = RealAdmissionBoundary().admit(
        admission_id="adm-1",
        audit_id="audit-1",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="broker",
        adapter_id="adapter",
        request_id="request",
        symbol="TEST",
    )
    fabricated = RealAdmission(
        genuine.admission_id,
        genuine.audit_id,
        genuine.status,
        genuine.broker_id,
        genuine.adapter_id,
        genuine.request_id,
        genuine.symbol,
        genuine.reasons,
    )

    assert genuine.status is RealAdmissionStatus.ADMITTED
    assert genuine.admitted
    assert fabricated == genuine
    assert fabricated is not genuine
    assert not fabricated.admitted


def test_blocked_admission_never_becomes_admitted():
    blocked = RealAdmissionBoundary().admit(
        admission_id="adm-blocked",
        audit_id="audit-1",
        audit_verified=True,
        authorization_active=False,
        safety_ready=True,
        broker_available=True,
        broker_id="broker",
        adapter_id="adapter",
        request_id="request",
        symbol="TEST",
    )
    assert blocked.status is RealAdmissionStatus.BLOCKED
    assert not blocked.admitted
