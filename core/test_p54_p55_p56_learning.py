import pytest

from core.p53_learning_hypothesis import LearningHypothesisBoundary
from core.p54_learning_validation import LearningValidationBoundary, ValidationStatus
from core.p55_trusted_knowledge import TrustedKnowledgeBoundary
from core.p56_controlled_knowledge_use import ControlledKnowledgeUseBoundary
from core.p52_learning_evidence import LearningEvidence


def hypothesis():
    evidence = LearningEvidence("cycle-53", "WIN", 9.0)
    return LearningHypothesisBoundary().propose(
        evidence, hypothesis_id="hyp-54", statement="A testable market condition may improve outcomes."
    )


def validation(status=ValidationStatus.VALIDATED):
    return LearningValidationBoundary().validate(
        hypothesis(),
        test_id="test-54",
        status=status,
        sample_size=20,
        observation="Explicit external test observation supplied for validation.",
    )


def test_p54_records_explicit_validation_without_inference():
    result = validation()
    assert result.hypothesis_id == "hyp-54"
    assert result.test_id == "test-54"
    assert result.status is ValidationStatus.VALIDATED
    assert result.sample_size == 20


def test_p54_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        LearningValidationBoundary().validate(None, test_id="t", status=ValidationStatus.VALIDATED, sample_size=1, observation="x")
    with pytest.raises(ValueError):
        LearningValidationBoundary().validate(hypothesis(), test_id="t", status=ValidationStatus.VALIDATED, sample_size=0, observation="x")
    with pytest.raises(ValueError):
        LearningValidationBoundary().validate(hypothesis(), test_id="t", status=ValidationStatus.VALIDATED, sample_size=1, observation="")


def test_p54_is_immutable():
    result = validation()
    with pytest.raises(Exception):
        result.status = ValidationStatus.REJECTED


def test_p55_promotes_only_validated_results():
    knowledge = TrustedKnowledgeBoundary().promote(
        validation(), knowledge_id="knowledge-55", statement="Validated knowledge statement."
    )
    assert knowledge.knowledge_id == "knowledge-55"
    assert knowledge.hypothesis_id == "hyp-54"
    assert knowledge.test_id == "test-54"

    for status in (ValidationStatus.REJECTED, ValidationStatus.INCONCLUSIVE):
        with pytest.raises(ValueError):
            TrustedKnowledgeBoundary().promote(
                validation(status), knowledge_id="knowledge-55", statement="blocked"
            )


def test_p55_requires_identity_and_statement():
    with pytest.raises(ValueError):
        TrustedKnowledgeBoundary().promote(validation(), knowledge_id="", statement="x")
    with pytest.raises(ValueError):
        TrustedKnowledgeBoundary().promote(validation(), knowledge_id="k", statement="")


def test_p56_authorizes_controlled_use_without_real_execution():
    knowledge = TrustedKnowledgeBoundary().promote(
        validation(), knowledge_id="knowledge-55", statement="Validated knowledge statement."
    )
    use = ControlledKnowledgeUseBoundary().authorize(
        knowledge, use_id="use-56", consumer="analysis"
    )
    assert use.knowledge_id == "knowledge-55"
    assert use.hypothesis_id == "hyp-54"
    assert use.test_id == "test-54"
    assert use.consumer == "analysis"
    assert use.real_execution_allowed is False


def test_p56_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        ControlledKnowledgeUseBoundary().authorize(None, use_id="u", consumer="analysis")
    knowledge = TrustedKnowledgeBoundary().promote(
        validation(), knowledge_id="knowledge-55", statement="Validated knowledge statement."
    )
    with pytest.raises(ValueError):
        ControlledKnowledgeUseBoundary().authorize(knowledge, use_id="", consumer="analysis")
    with pytest.raises(ValueError):
        ControlledKnowledgeUseBoundary().authorize(knowledge, use_id="u", consumer="")


def test_p56_is_immutable_and_real_execution_remains_blocked():
    knowledge = TrustedKnowledgeBoundary().promote(
        validation(), knowledge_id="knowledge-55", statement="Validated knowledge statement."
    )
    use = ControlledKnowledgeUseBoundary().authorize(knowledge, use_id="use-56", consumer="analysis")
    with pytest.raises(Exception):
        use.real_execution_allowed = True
    assert use.real_execution_allowed is False
