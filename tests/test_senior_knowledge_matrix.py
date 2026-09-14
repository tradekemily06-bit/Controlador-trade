from core.financial_market_curriculum import CurriculumDomain
from core.senior_knowledge_matrix import (
    KnowledgeEvidence,
    KnowledgeStatus,
    SeniorProfessionalKnowledgeMatrix,
)


def test_matrix_is_derived_from_curriculum_and_starts_unvalidated():
    matrix = SeniorProfessionalKnowledgeMatrix()
    assert matrix.records
    assert all(record.status is KnowledgeStatus.UNVALIDATED for record in matrix.records)
    assert all(record.execution_authorized is False for record in matrix.records)
    assert any(record.domain == CurriculumDomain.RISK_MANAGEMENT.value for record in matrix.records)


def test_validation_requires_complete_provenance_and_records_evidence():
    matrix = SeniorProfessionalKnowledgeMatrix()
    record = matrix.records[0]
    evidence = KnowledgeEvidence(
        source_id="source.example.1",
        source_title="Authoritative reference",
        source_version="2026-09",
        published_or_updated_at="2026-09-01",
        validated_at="2026-09-14",
        validator="senior-knowledge-validation",
        test_id="knowledge-test-001",
        evidence_note="Validated against the stated competency and independent evidence.",
    )
    updated = matrix.register_evidence(
        record.competency_id,
        evidence=evidence,
        reviewed_at="2026-09-14",
        next_review_reason="Reassess when the authoritative source changes.",
    )
    assert updated.status is KnowledgeStatus.VALIDATED
    assert updated.execution_authorized is False
    assert updated.evidence == (evidence,)


def test_reassessment_preserves_evidence_without_promoting_to_execution():
    matrix = SeniorProfessionalKnowledgeMatrix()
    record = matrix.records[0]
    evidence = KnowledgeEvidence(
        source_id="source.example.2",
        source_title="Reference",
        source_version="1",
        published_or_updated_at="2026-09-01",
        validated_at="2026-09-14",
        validator="validator",
        test_id="test-002",
        evidence_note="Evidence captured for later reassessment.",
    )
    matrix.register_evidence(record.competency_id, evidence=evidence, reviewed_at="2026-09-14")
    reassessed = matrix.mark_for_reassessment(record.competency_id, "source changed")
    assert reassessed.status is KnowledgeStatus.REASSESS
    assert reassessed.evidence == (evidence,)
    assert reassessed.next_review_reason == "source changed"
    assert reassessed.execution_authorized is False
