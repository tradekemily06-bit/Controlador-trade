from __future__ import annotations

from dataclasses import replace

from core.release_readiness import FinalReadinessEvidence, ReadinessState, assess_final_readiness


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
