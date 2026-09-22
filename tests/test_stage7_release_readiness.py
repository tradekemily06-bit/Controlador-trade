from __future__ import annotations

from dataclasses import replace

TARGET_SHA = "a" * 40

from core.release_readiness import (
    FinalReadinessEvidence,
    ReadinessEvidenceRef,
    ReadinessState,
    assess_final_readiness,
)


_REQUIRED_GATES = (
    "stage2_green",
    "stage3_green",
    "stage4_green",
    "stage5_green",
    "stage6_green",
    "side_doors_scanned",
    "threat_model_reviewed",
    "secrets_reviewed",
    "rollback_tested",
    "reconciliation_tested",
    "incident_response_tested",
    "demo_real_separation_tested",
    "legacy_compatibility_tested",
    "ci_green",
)


def _refs() -> tuple[ReadinessEvidenceRef, ...]:
    # These are deliberately test-only placeholders. They are not production
    # evidence and must never be copied into a real readiness assessment.
    return tuple(
        ReadinessEvidenceRef(gate, f"test-evidence-{gate}", f"test://{gate}", TARGET_SHA)
        for gate in _REQUIRED_GATES
    )


def _complete() -> FinalReadinessEvidence:
    return FinalReadinessEvidence(
        stage2_green=True,
        stage3_green=True,
        stage4_green=True,
        stage5_green=True,
        stage6_green=True,
        side_doors_scanned=True,
        threat_model_reviewed=True,
        secrets_reviewed=True,
        rollback_tested=True,
        reconciliation_tested=True,
        incident_response_tested=True,
        demo_real_separation_tested=True,
        legacy_compatibility_tested=True,
        ci_green=True,
        target_commit_sha=TARGET_SHA,
        evidence_refs=_refs(),
    )


def test_final_matrix_is_not_ready_when_any_gate_is_missing():
    evidence = replace(_complete(), reconciliation_tested=False)
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert assessment.missing == ("reconciliation_tested",)
    assert assessment.real_enabled is False


def test_complete_matrix_only_becomes_ready_for_review():
    assessment = assess_final_readiness(_complete())

    assert assessment.state is ReadinessState.READY_FOR_REVIEW
    assert assessment.missing == ()
    assert assessment.real_enabled is False


def test_final_matrix_requires_legacy_compatibility_evidence():
    evidence = replace(_complete(), legacy_compatibility_tested=False)
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert assessment.missing == ("legacy_compatibility_tested",)
    assert assessment.real_enabled is False


def test_green_gate_without_traceable_reference_is_not_ready():
    refs = tuple(ref for ref in _refs() if ref.gate != "rollback_tested")
    evidence = replace(_complete(), evidence_refs=refs)
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert assessment.missing == ("rollback_tested_evidence",)
    assert assessment.real_enabled is False


def test_false_gate_does_not_require_separate_evidence_reference():
    evidence = replace(
        _complete(),
        rollback_tested=False,
        evidence_refs=tuple(ref for ref in _refs() if ref.gate != "rollback_tested"),
    )
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert assessment.missing == ("rollback_tested",)


def test_evidence_reference_requires_identity_and_source():
    try:
        ReadinessEvidenceRef("ci_green", "", "test://ci", TARGET_SHA)
    except ValueError as exc:
        assert str(exc) == "evidence_id is required"
    else:
        raise AssertionError("missing evidence identity must be rejected")


def test_evidence_reference_fields_must_be_strings():
    for field_values in (
        (None, "id", "test://ci", TARGET_SHA),
        ("ci_green", 123, "test://ci", TARGET_SHA),
        ("ci_green", "id", object(), TARGET_SHA),
    ):
        try:
            ReadinessEvidenceRef(*field_values)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed evidence identity must be rejected")


def test_non_evidence_ref_object_is_fail_closed():
    evidence = replace(_complete(), evidence_refs=("not-an-evidence-ref",))
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert assessment.missing == (
        "invalid_evidence_ref",
        *(f"{gate}_evidence" for gate in _REQUIRED_GATES),
    )
    assert assessment.real_enabled is False


def test_unknown_evidence_gate_is_not_accepted():
    evidence = replace(
        _complete(),
        evidence_refs=_refs() + (ReadinessEvidenceRef("unknown_gate", "id", "test://unknown", TARGET_SHA),),
    )
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert "invalid_evidence_gate" in assessment.missing


def test_duplicate_evidence_gate_is_not_accepted():
    duplicate = ReadinessEvidenceRef("ci_green", "second-ci", "test://ci-2", TARGET_SHA)
    evidence = replace(_complete(), evidence_refs=_refs() + (duplicate,))
    assessment = assess_final_readiness(evidence)

    assert assessment.state is ReadinessState.NOT_READY
    assert "duplicate_evidence_gate" in assessment.missing


def test_stale_evidence_commit_is_not_ready():
    stale = replace(
        _complete(),
        evidence_refs=tuple(
            ReadinessEvidenceRef(ref.gate, ref.evidence_id, ref.source_ref, "b" * 40)
            if ref.gate == "ci_green" else ref
            for ref in _refs()
        ),
    )
    assessment = assess_final_readiness(stale)
    assert assessment.state is ReadinessState.NOT_READY
    assert assessment.missing == ("stale_evidence_commit",)
    assert assessment.real_enabled is False
