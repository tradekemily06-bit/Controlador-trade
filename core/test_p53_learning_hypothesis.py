import pytest

from core.p52_learning_evidence import LearningEvidence
from core.p53_learning_hypothesis import LearningHypothesisBoundary


def evidence():
    return LearningEvidence("cycle-53", "WIN", 9.0)


def test_proposes_unvalidated_hypothesis_from_factual_evidence():
    hypothesis = LearningHypothesisBoundary().propose(
        evidence(), hypothesis_id="hyp-53", statement="This setup may improve outcome quality."
    )
    assert hypothesis.hypothesis_id == "hyp-53"
    assert hypothesis.evidence_cycle_id == "cycle-53"
    assert hypothesis.validated is False


def test_rejects_non_factual_evidence():
    with pytest.raises(ValueError):
        LearningHypothesisBoundary().propose(
            LearningEvidence("cycle-53", "WIN", 9.0, factual=False),
            hypothesis_id="hyp-53",
            statement="test",
        )


@pytest.mark.parametrize("hypothesis_id,statement", [("", "test"), ("id", "")])
def test_requires_identity_and_statement(hypothesis_id, statement):
    with pytest.raises(ValueError):
        LearningHypothesisBoundary().propose(evidence(), hypothesis_id=hypothesis_id, statement=statement)


def test_invalid_evidence_fails_closed():
    with pytest.raises(ValueError):
        LearningHypothesisBoundary().propose(None, hypothesis_id="hyp-53", statement="test")


def test_hypothesis_is_immutable():
    hypothesis = LearningHypothesisBoundary().propose(
        evidence(), hypothesis_id="hyp-53", statement="test"
    )
    with pytest.raises(Exception):
        hypothesis.validated = True
