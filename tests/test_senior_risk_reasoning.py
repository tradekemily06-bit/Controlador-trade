from __future__ import annotations

from core.senior_risk_reasoning import (
    RiskDomain,
    RiskKnowledgeStatus,
    RiskObservation,
    SeniorRiskReasoner,
)


def test_risk_reasoning_covers_manual_and_autonomous_use_without_authorizing_execution() -> None:
    result = SeniorRiskReasoner().assess(
        (
            RiskObservation(RiskDomain.CAPITAL, "capital exposure known", True),
            RiskObservation(RiskDomain.LEVERAGE_MARGIN, "margin state known", True),
            RiskObservation(RiskDomain.LIQUIDITY, "liquidity observed", True),
            RiskObservation(RiskDomain.EXECUTION, "execution state known", True),
        ),
        available_domains=(
            RiskDomain.CAPITAL,
            RiskDomain.LEVERAGE_MARGIN,
            RiskDomain.LIQUIDITY,
            RiskDomain.EXECUTION,
        ),
    )

    assert result.status is RiskKnowledgeStatus.ASSESSED
    assert result.unknowns == ()
    assert result.execution_authorized is False
    assert any("alavancagem" in q.lower() for q in result.questions)


def test_missing_material_risk_domain_forces_reassessment() -> None:
    result = SeniorRiskReasoner().assess(
        (RiskObservation(RiskDomain.CAPITAL, "capital known", True),),
        available_domains=(RiskDomain.CAPITAL, RiskDomain.LIQUIDITY),
    )

    assert result.status is RiskKnowledgeStatus.REASSESS
    assert result.unknowns == ("LIQUIDITY",)
    assert any("liquidez" in q.lower() for q in result.questions)
    assert result.execution_authorized is False


def test_no_risk_facts_never_becomes_safe_by_assumption() -> None:
    result = SeniorRiskReasoner().assess(
        available_domains=(RiskDomain.CAPITAL, RiskDomain.DRAWDOWN)
    )

    assert result.status is RiskKnowledgeStatus.INSUFFICIENT
    assert result.unknowns == ("CAPITAL", "DRAWDOWN")
    assert result.execution_authorized is False


def test_duplicate_domain_does_not_create_fake_confluence() -> None:
    result = SeniorRiskReasoner().assess(
        (
            RiskObservation(RiskDomain.LIQUIDITY, "liquidity A", True),
            RiskObservation(RiskDomain.LIQUIDITY, "liquidity B", True),
        ),
        available_domains=(RiskDomain.LIQUIDITY,),
    )

    assert len(result.observations) == 1
    assert result.observations[0].statement == "liquidity A"
