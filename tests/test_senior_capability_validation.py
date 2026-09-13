from core.p57_knowledge_memory import KnowledgeMemoryRecord
from core.p83_validation_decision import ValidationDecision, ValidationDecisionStatus
from core.senior_capability_validation import (
    CapabilityTrust,
    SeniorCapabilityEvidence,
    admit_senior_capability,
)


def _validation(status=ValidationDecisionStatus.VALIDATED):
    return ValidationDecision(
        decision_id="decision-1",
        result_id="result-1",
        test_id="test-1",
        hypothesis_id="hypothesis-1",
        status=status,
        rationale="validated by test",
    )


def _memory(test_id="test-1", hypothesis_id="hypothesis-1"):
    return KnowledgeMemoryRecord(
        memory_id="memory-1",
        knowledge_id="knowledge-1",
        hypothesis_id=hypothesis_id,
        test_id=test_id,
        statement="validated capability evidence",
    )


def test_capability_requires_validation_and_memory_for_trusted_status():
    evidence = SeniorCapabilityEvidence("fx-context", "forex")
    result = admit_senior_capability(evidence, validation=None, memory=None)
    assert result.trust is CapabilityTrust.UNVALIDATED


def test_matching_positive_validation_and_memory_are_admitted():
    evidence = SeniorCapabilityEvidence("fx-context", "forex")
    result = admit_senior_capability(evidence, validation=_validation(), memory=_memory())
    assert result.trust is CapabilityTrust.VALIDATED
    assert result.validation_decision_id == "decision-1"
    assert result.memory_id == "memory-1"


def test_negative_validation_never_becomes_trusted():
    evidence = SeniorCapabilityEvidence("fx-context", "forex")
    result = admit_senior_capability(
        evidence,
        validation=_validation(ValidationDecisionStatus.REJECTED),
        memory=_memory(),
    )
    assert result.trust is CapabilityTrust.UNVALIDATED


def test_mismatched_provenance_is_not_trusted():
    evidence = SeniorCapabilityEvidence("fx-context", "forex")
    result = admit_senior_capability(
        evidence,
        validation=_validation(),
        memory=_memory(test_id="other-test"),
    )
    assert result.trust is CapabilityTrust.INCONSISTENT
