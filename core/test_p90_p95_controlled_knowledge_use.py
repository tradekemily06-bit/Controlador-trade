import pytest

from core.p88_controlled_use_authorization import ControlledUseAuthorization
from core.p89_knowledge_governance_closure import KnowledgeGovernanceClosure
from core.p90_controlled_knowledge_use import ControlledKnowledgeUseBoundary
from core.p91_knowledge_use_observation import KnowledgeUseObservationBoundary
from core.p92_knowledge_use_evaluation import KnowledgeUseEvaluationBoundary, KnowledgeUseEvaluationStatus
from core.p93_knowledge_use_disposition import KnowledgeUseDispositionBoundary, KnowledgeUseDisposition
from core.p94_controlled_operational_admission import ControlledOperationalAdmissionBoundary
from core.p95_controlled_operational_closure import ControlledOperationalClosureBoundary


def artifacts():
    auth = ControlledUseAuthorization("u0", "i0", "a0", "k0", "h0", "lab")
    closure = KnowledgeGovernanceClosure("c0", "u0", "i0", "a0", "k0", "h0", "lab")
    return auth, closure


def test_p90_p95_flow_preserves_provenance_and_blocks_real():
    auth, closure = artifacts()
    use = ControlledKnowledgeUseBoundary().request(auth, closure, use_id="use1", purpose="controlled evaluation")
    obs = KnowledgeUseObservationBoundary().record(use, observation_id="obs1", sample_size=5, observation="facts")
    evaluation = KnowledgeUseEvaluationBoundary().evaluate(obs, evaluation_id="eval1", status=KnowledgeUseEvaluationStatus.SUPPORTED, rationale="supported")
    disposition = KnowledgeUseDispositionBoundary().decide(evaluation, disposition_id="disp1", disposition=KnowledgeUseDisposition.RETAIN, rationale="retain")
    admission = ControlledOperationalAdmissionBoundary().admit(disposition, admission_id="op1")
    closure2 = ControlledOperationalClosureBoundary().close(admission, closure_id="close1")
    assert closure2.knowledge_id == "k0"
    assert closure2.hypothesis_id == "h0"
    assert closure2.scope == "CONTROLLED"
    assert closure2.real_execution_allowed is False


def test_p90_rejects_mismatched_governance():
    auth, closure = artifacts()
    bad = KnowledgeGovernanceClosure("c0", "different", "i0", "a0", "k0", "h0", "lab")
    with pytest.raises(ValueError):
        ControlledKnowledgeUseBoundary().request(auth, bad, use_id="u", purpose="x")


def test_p91_requires_positive_sample():
    auth, closure = artifacts()
    use = ControlledKnowledgeUseBoundary().request(auth, closure, use_id="u", purpose="x")
    with pytest.raises(ValueError):
        KnowledgeUseObservationBoundary().record(use, observation_id="o", sample_size=0, observation="x")


def test_p94_requires_retain():
    auth, closure = artifacts()
    use = ControlledKnowledgeUseBoundary().request(auth, closure, use_id="u", purpose="x")
    obs = KnowledgeUseObservationBoundary().record(use, observation_id="o", sample_size=1, observation="x")
    evaluation = KnowledgeUseEvaluationBoundary().evaluate(obs, evaluation_id="e", status=KnowledgeUseEvaluationStatus.NOT_SUPPORTED, rationale="not")
    disposition = KnowledgeUseDispositionBoundary().decide(evaluation, disposition_id="d", disposition=KnowledgeUseDisposition.REVIEW, rationale="review")
    with pytest.raises(ValueError):
        ControlledOperationalAdmissionBoundary().admit(disposition, admission_id="a")


def test_p95_is_immutable():
    auth, closure = artifacts()
    use = ControlledKnowledgeUseBoundary().request(auth, closure, use_id="u", purpose="x")
    obs = KnowledgeUseObservationBoundary().record(use, observation_id="o", sample_size=1, observation="x")
    evaluation = KnowledgeUseEvaluationBoundary().evaluate(obs, evaluation_id="e", status=KnowledgeUseEvaluationStatus.SUPPORTED, rationale="yes")
    disposition = KnowledgeUseDispositionBoundary().decide(evaluation, disposition_id="d", disposition=KnowledgeUseDisposition.RETAIN, rationale="retain")
    admission = ControlledOperationalAdmissionBoundary().admit(disposition, admission_id="a")
    result = ControlledOperationalClosureBoundary().close(admission, closure_id="c")
    with pytest.raises((AttributeError, TypeError)):
        result.status = "OPEN"
