import pytest

from core.p79_validation_admission import ValidationAdmission
from core.p80_validation_specification import ValidationSpecificationBoundary
from core.p81_validation_run import ValidationRunBoundary
from core.p82_validation_result import ValidationResultBoundary, ValidationResultStatus
from core.p83_validation_decision import ValidationDecisionBoundary, ValidationDecisionStatus
from core.p84_knowledge_promotion_admission import KnowledgePromotionAdmissionBoundary
from core.p85_trusted_knowledge_release import TrustedKnowledgeReleaseBoundary


def admission():
    return ValidationAdmission("adm", "hyp", "ctx", "hand", "statement")


def test_p80_to_p85_preserves_provenance():
    spec = ValidationSpecificationBoundary().specify(admission(), test_id="t1", environment="lab", criteria="criterion")
    run = ValidationRunBoundary().record(spec, run_id="run1", sample_size=10, observation="observed")
    result = ValidationResultBoundary().conclude(run, result_id="res1", status=ValidationResultStatus.POSITIVE, rationale="positive")
    decision = ValidationDecisionBoundary().decide(result, decision_id="dec1", status=ValidationDecisionStatus.VALIDATED, rationale="validated")
    promotion = KnowledgePromotionAdmissionBoundary().admit(decision, admission_id="prom1")
    release = TrustedKnowledgeReleaseBoundary().release(promotion, knowledge_id="know1", statement="statement")
    assert release.hypothesis_id == "hyp"
    assert release.decision_id == "dec1"
    assert release.result_id == "res1"
    assert release.real_execution_allowed is False
    with pytest.raises(Exception):
        release.release_status = "BLOCKED"


def test_p80_requires_admitted_hypothesis():
    blocked = ValidationAdmission("x", "h", "c", "h", "s", status="BLOCKED")
    with pytest.raises(ValueError):
        ValidationSpecificationBoundary().specify(blocked, test_id="t", environment="lab", criteria="c")


def test_p81_requires_positive_sample():
    spec = ValidationSpecificationBoundary().specify(admission(), test_id="t", environment="lab", criteria="c")
    with pytest.raises(ValueError):
        ValidationRunBoundary().record(spec, run_id="r", sample_size=0, observation="x")


def test_p83_rejects_incompatible_validation():
    spec = ValidationSpecificationBoundary().specify(admission(), test_id="t", environment="lab", criteria="c")
    run = ValidationRunBoundary().record(spec, run_id="r", sample_size=1, observation="x")
    result = ValidationResultBoundary().conclude(run, result_id="res", status=ValidationResultStatus.NEGATIVE, rationale="negative")
    with pytest.raises(ValueError):
        ValidationDecisionBoundary().decide(result, decision_id="d", status=ValidationDecisionStatus.VALIDATED, rationale="wrong")


def test_p84_requires_validated_decision():
    spec = ValidationSpecificationBoundary().specify(admission(), test_id="t", environment="lab", criteria="c")
    run = ValidationRunBoundary().record(spec, run_id="r", sample_size=1, observation="x")
    result = ValidationResultBoundary().conclude(run, result_id="res", status=ValidationResultStatus.INCONCLUSIVE, rationale="unclear")
    decision = ValidationDecisionBoundary().decide(result, decision_id="d", status=ValidationDecisionStatus.INCONCLUSIVE, rationale="unclear")
    with pytest.raises(ValueError):
        KnowledgePromotionAdmissionBoundary().admit(decision, admission_id="p")
