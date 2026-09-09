import pytest

from core.p88_controlled_use_authorization import ControlledUseAuthorization
from core.p89_knowledge_governance_closure import KnowledgeGovernanceClosure
from core.p90_controlled_knowledge_use import ControlledKnowledgeUseBoundary
from core.p91_knowledge_use_observation import KnowledgeUseObservationBoundary
from core.p92_knowledge_use_evaluation import KnowledgeUseEvaluationBoundary, KnowledgeUseEvaluationStatus
from core.p93_knowledge_use_disposition import KnowledgeUseDispositionBoundary, KnowledgeUseDisposition
from core.p94_controlled_operational_admission import ControlledOperationalAdmissionBoundary
from core.p95_controlled_operational_closure import ControlledOperationalClosureBoundary
from core.p96_operational_observation import OperationalObservationBoundary
from core.p97_operational_assessment import OperationalAssessmentBoundary, OperationalAssessmentStatus
from core.p98_operational_disposition import OperationalDispositionBoundary, OperationalDisposition
from core.p99_operational_feedback_closure import OperationalFeedbackClosureBoundary


def p95_closure():
    auth = ControlledUseAuthorization("u0", "i0", "a0", "k0", "h0", "lab")
    governance = KnowledgeGovernanceClosure("c0", "u0", "i0", "a0", "k0", "h0", "lab")
    use = ControlledKnowledgeUseBoundary().request(auth, governance, use_id="use1", purpose="controlled evaluation")
    obs = KnowledgeUseObservationBoundary().record(use, observation_id="obs1", sample_size=3, observation="facts")
    evaluation = KnowledgeUseEvaluationBoundary().evaluate(obs, evaluation_id="eval1", status=KnowledgeUseEvaluationStatus.SUPPORTED, rationale="supported")
    disposition = KnowledgeUseDispositionBoundary().decide(evaluation, disposition_id="disp1", disposition=KnowledgeUseDisposition.RETAIN, rationale="retain")
    admission = ControlledOperationalAdmissionBoundary().admit(disposition, admission_id="op1")
    return ControlledOperationalClosureBoundary().close(admission, closure_id="op-close")


def test_p96_p99_preserve_provenance_and_block_real():
    operational = p95_closure()
    observation = OperationalObservationBoundary().record(operational, observation_id="o96", sample_size=4, observation="explicit facts")
    assessment = OperationalAssessmentBoundary().assess(observation, assessment_id="a97", status=OperationalAssessmentStatus.SUPPORTED, rationale="supported")
    disposition = OperationalDispositionBoundary().decide(assessment, disposition_id="d98", disposition=OperationalDisposition.RETAIN, rationale="retain")
    closure = OperationalFeedbackClosureBoundary().close(disposition, closure_id="f99")
    assert closure.operational_closure_id == "op-close"
    assert closure.admission_id == "op1"
    assert closure.knowledge_id == "k0"
    assert closure.hypothesis_id == "h0"
    assert closure.disposition == "RETAIN"
    assert closure.real_execution_allowed is False


def test_p96_requires_closed_p95_and_positive_sample():
    operational = p95_closure()
    with pytest.raises(ValueError):
        OperationalObservationBoundary().record(operational, observation_id="o", sample_size=0, observation="facts")
    with pytest.raises(ValueError):
        OperationalObservationBoundary().record(None, observation_id="o", sample_size=1, observation="facts")


def test_p97_requires_explicit_status_and_rationale():
    observation = OperationalObservationBoundary().record(p95_closure(), observation_id="o", sample_size=1, observation="facts")
    with pytest.raises(ValueError):
        OperationalAssessmentBoundary().assess(observation, assessment_id="a", status="SUPPORTED", rationale="x")
    with pytest.raises(ValueError):
        OperationalAssessmentBoundary().assess(observation, assessment_id="a", status=OperationalAssessmentStatus.SUPPORTED, rationale="")


def test_p98_accepts_only_declared_disposition_enum():
    observation = OperationalObservationBoundary().record(p95_closure(), observation_id="o", sample_size=1, observation="facts")
    assessment = OperationalAssessmentBoundary().assess(observation, assessment_id="a", status=OperationalAssessmentStatus.INCONCLUSIVE, rationale="unclear")
    with pytest.raises(ValueError):
        OperationalDispositionBoundary().decide(assessment, disposition_id="d", disposition="RETAIN", rationale="x")


def test_p99_is_immutable():
    observation = OperationalObservationBoundary().record(p95_closure(), observation_id="o", sample_size=1, observation="facts")
    assessment = OperationalAssessmentBoundary().assess(observation, assessment_id="a", status=OperationalAssessmentStatus.SUPPORTED, rationale="yes")
    disposition = OperationalDispositionBoundary().decide(assessment, disposition_id="d", disposition=OperationalDisposition.REVIEW, rationale="review")
    closure = OperationalFeedbackClosureBoundary().close(disposition, closure_id="f")
    with pytest.raises((AttributeError, TypeError)):
        closure.status = "OPEN"
