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


def applied():
    evidence = LearningEvidence("cycle-64", "WIN", 9.0)
    hypothesis = LearningHypothesisBoundary().propose(evidence, hypothesis_id="h-64", statement="testable condition")
    validation = LearningValidationBoundary().validate(hypothesis, test_id="t-64", status=ValidationStatus.VALIDATED, sample_size=20, observation="explicit observation")
    knowledge = TrustedKnowledgeBoundary().promote(validation, knowledge_id="k-64", statement="validated knowledge")
    memory = KnowledgeMemoryBoundary().record(knowledge, memory_id="m-64")
    audit = MemoryAuditBoundary().audit(memory)
    run = KnowledgeLabBoundary().run(audit, memory, lab_id="lab-64", scenario="controlled scenario")
    proposal = AdaptationProposalBoundary().propose(run, proposal_id="p-64", rationale="controlled adaptation")
    evaluation = AdaptationEvaluationBoundary().evaluate(proposal, status=EvaluationStatus.APPROVED, rationale="approved")
    return ControlledAdaptationBoundary().apply(proposal, evaluation, application_id="a-64")


def test_p64_activation_preserves_provenance_and_blocks_real():
    result = AdaptationActivationBoundary().activate(applied(), activation_id="act-64", context="controlled context")
    assert result.proposal_id == "p-64"
    assert result.application_id == "a-64"
    assert result.real_execution_allowed is False
    with pytest.raises(Exception):
        result.context = "changed"


def test_p64_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        AdaptationActivationBoundary().activate(None, activation_id="x", context="ctx")
    with pytest.raises(ValueError):
        AdaptationActivationBoundary().activate(applied(), activation_id="", context="ctx")


def test_p65_records_only_explicit_observation():
    activation = AdaptationActivationBoundary().activate(applied(), activation_id="act-65", context="controlled")
    result = AdaptationObservationBoundary().record(
        activation, observation_id="obs-65", sample_size=12, observation="explicit post-activation observation"
    )
    assert result.proposal_id == "p-64"
    assert result.activation_id == "act-65"
    assert result.sample_size == 12
    with pytest.raises(ValueError):
        AdaptationObservationBoundary().record(activation, observation_id="obs", sample_size=0, observation="x")


def test_p66_evaluation_is_explicit_and_immutable():
    activation = AdaptationActivationBoundary().activate(applied(), activation_id="act-66", context="controlled")
    observation = AdaptationObservationBoundary().record(
        activation, observation_id="obs-66", sample_size=15, observation="explicit observation"
    )
    result = PostAdaptationEvaluationBoundary().evaluate(
        observation, status=PostAdaptationStatus.INCONCLUSIVE, rationale="insufficient evidence for a conclusion"
    )
    assert result.proposal_id == observation.proposal_id
    assert result.application_id == observation.application_id
    assert result.observation_id == "obs-66"
    with pytest.raises(Exception):
        result.status = PostAdaptationStatus.SUPPORTED


def test_p66_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        PostAdaptationEvaluationBoundary().evaluate(
            None, status=PostAdaptationStatus.SUPPORTED, rationale="x"
        )
    activation = AdaptationActivationBoundary().activate(applied(), activation_id="act", context="controlled")
    observation = AdaptationObservationBoundary().record(
        activation, observation_id="obs", sample_size=1, observation="x"
    )
    with pytest.raises(ValueError):
        PostAdaptationEvaluationBoundary().evaluate(
            observation, status=PostAdaptationStatus.SUPPORTED, rationale=""
        )
