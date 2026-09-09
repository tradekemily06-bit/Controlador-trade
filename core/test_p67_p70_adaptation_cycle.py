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
from core.p64_adaptation_activation import AdaptationActivationBoundary
from core.p65_adaptation_observation import AdaptationObservationBoundary
from core.p66_adaptation_evaluation import PostAdaptationEvaluationBoundary, PostAdaptationStatus
from core.p67_adaptation_cycle import AdaptationCycleBoundary
from core.p68_adaptation_disposition import AdaptationDispositionBoundary, Disposition
from core.p69_cycle_eligibility import Eligibility, NextCycleEligibilityBoundary
from core.p70_adaptation_cycle_closure import AdaptationCycleClosureBoundary


def evaluation():
    evidence = LearningEvidence("cycle-67", "WIN", 9.0)
    hypothesis = LearningHypothesisBoundary().propose(evidence, hypothesis_id="h-67", statement="condition")
    validation = LearningValidationBoundary().validate(hypothesis, test_id="t-67", status=ValidationStatus.VALIDATED, sample_size=20, observation="observation")
    knowledge = TrustedKnowledgeBoundary().promote(validation, knowledge_id="k-67", statement="knowledge")
    memory = KnowledgeMemoryBoundary().record(knowledge, memory_id="m-67")
    audit = MemoryAuditBoundary().audit(memory)
    run = KnowledgeLabBoundary().run(audit, memory, lab_id="lab-67", scenario="scenario")
    proposal = AdaptationProposalBoundary().propose(run, proposal_id="p-67", rationale="controlled")
    approval = AdaptationEvaluationBoundary().evaluate(proposal, status=EvaluationStatus.APPROVED, rationale="approved")
    application = ControlledAdaptationBoundary().apply(proposal, approval, application_id="a-67")
    activation = AdaptationActivationBoundary().activate(application, activation_id="act-67", context="controlled")
    observation = AdaptationObservationBoundary().record(activation, observation_id="obs-67", sample_size=10, observation="explicit")
    return PostAdaptationEvaluationBoundary().evaluate(observation, status=PostAdaptationStatus.INCONCLUSIVE, rationale="not enough evidence")


def test_p67_to_p70_preserve_provenance_and_close():
    cycle = AdaptationCycleBoundary().consolidate(evaluation())
    disposition = AdaptationDispositionBoundary().decide(cycle, disposition=Disposition.REVIEW, rationale="manual review")
    eligibility = NextCycleEligibilityBoundary().evaluate(disposition, eligibility=Eligibility.REVIEW_REQUIRED, rationale="review before next cycle")
    closure = AdaptationCycleClosureBoundary().close(eligibility, summary="cycle closed factually")
    assert closure.proposal_id == "p-67"
    assert closure.application_id == "a-67"
    assert closure.observation_id == "obs-67"
    assert closure.disposition == "REVIEW"
    assert closure.eligibility == "REVIEW_REQUIRED"
    assert closure.real_execution_allowed is False
    with pytest.raises(Exception):
        closure.summary = "changed"


def test_p67_rejects_invalid():
    with pytest.raises(ValueError):
        AdaptationCycleBoundary().consolidate(None)


def test_p68_rejects_empty_rationale():
    cycle = AdaptationCycleBoundary().consolidate(evaluation())
    with pytest.raises(ValueError):
        AdaptationDispositionBoundary().decide(cycle, disposition=Disposition.RETAIN, rationale="")


def test_p69_rejects_invalid_cycle_disposition():
    with pytest.raises(ValueError):
        NextCycleEligibilityBoundary().evaluate(None, eligibility=Eligibility.ELIGIBLE, rationale="x")


def test_p70_requires_summary():
    cycle = AdaptationCycleBoundary().consolidate(evaluation())
    disposition = AdaptationDispositionBoundary().decide(cycle, disposition=Disposition.RETIRE, rationale="retire")
    eligibility = NextCycleEligibilityBoundary().evaluate(disposition, eligibility=Eligibility.NOT_ELIGIBLE, rationale="closed")
    with pytest.raises(ValueError):
        AdaptationCycleClosureBoundary().close(eligibility, summary="")
