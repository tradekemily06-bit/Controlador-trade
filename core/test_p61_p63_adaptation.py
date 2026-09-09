import pytest

from core.p53_learning_hypothesis import LearningHypothesisBoundary
from core.p52_learning_evidence import LearningEvidence
from core.p54_learning_validation import LearningValidationBoundary, ValidationStatus
from core.p55_trusted_knowledge import TrustedKnowledgeBoundary
from core.p57_knowledge_memory import KnowledgeMemoryBoundary
from core.p58_memory_audit import MemoryAuditBoundary
from core.p59_knowledge_lab import KnowledgeLabBoundary
from core.p60_adaptation_proposal import AdaptationProposalBoundary
from core.p61_adaptation_evaluation import AdaptationEvaluationBoundary, EvaluationStatus
from core.p62_controlled_adaptation import ControlledAdaptationBoundary
from core.p63_adaptation_audit import AdaptationCycleAuditBoundary, AuditState


def proposal():
    evidence = LearningEvidence("cycle-61", "WIN", 9.0)
    hypothesis = LearningHypothesisBoundary().propose(evidence, hypothesis_id="h-61", statement="testable condition")
    validation = LearningValidationBoundary().validate(hypothesis, test_id="t-61", status=ValidationStatus.VALIDATED, sample_size=20, observation="explicit observation")
    knowledge = TrustedKnowledgeBoundary().promote(validation, knowledge_id="k-61", statement="validated knowledge")
    memory = KnowledgeMemoryBoundary().record(knowledge, memory_id="m-61")
    audit = MemoryAuditBoundary().audit(memory)
    run = KnowledgeLabBoundary().run(audit, memory, lab_id="lab-61", scenario="controlled scenario")
    return AdaptationProposalBoundary().propose(run, proposal_id="p-61", rationale="lab result requires review")


def test_p61_evaluation_is_explicit_and_immutable():
    result = AdaptationEvaluationBoundary().evaluate(proposal(), status=EvaluationStatus.APPROVED, rationale="approved after review")
    assert result.proposal_id == "p-61"
    assert result.status is EvaluationStatus.APPROVED
    with pytest.raises(Exception):
        result.status = EvaluationStatus.REJECTED


def test_p61_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        AdaptationEvaluationBoundary().evaluate(None, status=EvaluationStatus.APPROVED, rationale="x")


def test_p62_requires_matching_approval_and_never_enables_real_execution():
    prop = proposal()
    evaluation = AdaptationEvaluationBoundary().evaluate(prop, status=EvaluationStatus.APPROVED, rationale="approved")
    applied = ControlledAdaptationBoundary().apply(prop, evaluation, application_id="a-62")
    assert applied.proposal_id == prop.proposal_id
    assert applied.real_execution_allowed is False
    with pytest.raises(Exception):
        applied.real_execution_allowed = True
    for status in (EvaluationStatus.REJECTED, EvaluationStatus.NEEDS_REVIEW):
        blocked = AdaptationEvaluationBoundary().evaluate(prop, status=status, rationale="not approved")
        with pytest.raises(ValueError):
            ControlledAdaptationBoundary().apply(prop, blocked, application_id="blocked")


def test_p62_rejects_mismatched_artifacts_and_reapplication():
    prop = proposal()
    evaluation = AdaptationEvaluationBoundary().evaluate(prop, status=EvaluationStatus.APPROVED, rationale="approved")
    with pytest.raises(ValueError):
        ControlledAdaptationBoundary().apply(prop, evaluation, application_id="")

    other_knowledge = TrustedKnowledgeBoundary().promote(
        LearningValidationBoundary().validate(
            LearningHypothesisBoundary().propose(
                LearningEvidence("c2", "WIN", 9.0), hypothesis_id="other2", statement="s"
            ),
            test_id="t2", status=ValidationStatus.VALIDATED, sample_size=2, observation="o"
        ),
        knowledge_id="k2", statement="s"
    )
    other_memory = KnowledgeMemoryBoundary().record(other_knowledge, memory_id="m2")
    other_audit = MemoryAuditBoundary().audit(other_memory)
    other_run = KnowledgeLabBoundary().run(other_audit, other_memory, lab_id="lab2", scenario="s")
    mismatched = AdaptationEvaluationBoundary().evaluate(
        AdaptationProposalBoundary().propose(other_run, proposal_id="other-proposal", rationale="other"),
        status=EvaluationStatus.APPROVED, rationale="approved"
    )
    with pytest.raises(ValueError):
        ControlledAdaptationBoundary().apply(prop, mismatched, application_id="bad")


def test_p63_closes_only_matching_factual_cycle():
    prop = proposal()
    evaluation = AdaptationEvaluationBoundary().evaluate(prop, status=EvaluationStatus.APPROVED, rationale="approved")
    application = ControlledAdaptationBoundary().apply(prop, evaluation, application_id="a-63")
    audit = AdaptationCycleAuditBoundary().close(evaluation, application, summary="proposal, evaluation and application were recorded")
    assert audit.state is AuditState.COMPLETE
    assert audit.proposal_id == prop.proposal_id
    assert audit.application_id == "a-63"
    with pytest.raises(Exception):
        audit.state = AuditState.BLOCKED
