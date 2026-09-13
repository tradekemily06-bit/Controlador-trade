import pytest

from core.market_learning_cycle import (
    EvidenceStatus,
    KnowledgeKind,
    MarketEvidence,
    assess_learning,
)


def ev(i: str, status: EvidenceStatus) -> MarketEvidence:
    return MarketEvidence(i, f"evidence {i}", status, 0.8, "market-analysis")


def test_support_requires_validation_and_memory_and_never_authorizes_execution():
    result = assess_learning(
        "hyp-1", KnowledgeKind.DISCOVERY, [ev("e1", EvidenceStatus.SUPPORTED)]
    )
    assert result.conclusion is EvidenceStatus.SUPPORTED
    assert result.test_required is True
    assert result.memory_required is True
    assert result.execution_authorized is False


def test_conflicting_evidence_is_not_forced_into_a_trade_conclusion():
    result = assess_learning(
        "hyp-2",
        KnowledgeKind.USER_KNOWLEDGE,
        [ev("support", EvidenceStatus.SUPPORTED), ev("contra", EvidenceStatus.CONTRADICTED)],
        ["Does the movement sustain after the apparent breakout?"],
    )
    assert result.conclusion is EvidenceStatus.CONFLICTING
    assert result.unanswered_questions
    assert result.execution_authorized is False


def test_no_evidence_is_insufficient():
    result = assess_learning("hyp-3", KnowledgeKind.SYSTEM_KNOWLEDGE)
    assert result.conclusion is EvidenceStatus.INSUFFICIENT
    assert result.test_required is True
    assert result.memory_required is True


def test_invalid_strength_fails_closed():
    with pytest.raises(ValueError):
        MarketEvidence("e1", "x", EvidenceStatus.SUPPORTED, 1.1, "source")
