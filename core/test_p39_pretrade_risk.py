import pytest

from core.p39_pretrade_risk import (
    PreTradeRiskEvaluator,
    RiskDecision,
    RiskLimits,
    RiskProposal,
)


def _limits():
    return RiskLimits(max_order_amount=100, max_total_exposure=250)


def test_approves_within_limits():
    result = PreTradeRiskEvaluator().evaluate(RiskProposal(50, 100), _limits())
    assert result.decision is RiskDecision.APPROVED
    assert result.projected_exposure == 150


def test_blocks_order_limit():
    result = PreTradeRiskEvaluator().evaluate(RiskProposal(101, 0), _limits())
    assert result.decision is RiskDecision.BLOCKED


def test_blocks_projected_exposure_limit():
    result = PreTradeRiskEvaluator().evaluate(RiskProposal(60, 200), _limits())
    assert result.decision is RiskDecision.BLOCKED
    assert result.projected_exposure == 260


@pytest.mark.parametrize(
    "proposal,limits",
    [
        (RiskProposal(0, 0), _limits()),
        (RiskProposal(-1, 0), _limits()),
        (RiskProposal(10, -1), _limits()),
        (RiskProposal(10, 0), RiskLimits(0, 100)),
        (RiskProposal(10, 0), RiskLimits(100, -1)),
    ],
)
def test_invalid_risk_values_block(proposal, limits):
    assert PreTradeRiskEvaluator().evaluate(proposal, limits).decision is RiskDecision.BLOCKED


def test_non_finite_values_block():
    result = PreTradeRiskEvaluator().evaluate(RiskProposal(float("nan"), 0), _limits())
    assert result.decision is RiskDecision.BLOCKED


def test_invalid_types_fail_closed():
    evaluator = PreTradeRiskEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate(object(), _limits())
    with pytest.raises(ValueError):
        evaluator.evaluate(RiskProposal(1, 0), object())
