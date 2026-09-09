import pytest

from core.p40_risk_budget import BudgetDecision, RiskBudgetEvaluator, RiskBudgetLimits, RiskBudgetState


def test_approves_within_daily_budget():
    result = RiskBudgetEvaluator().evaluate(RiskBudgetState(20, 2), RiskBudgetLimits(100, 5), 30)
    assert result.decision is BudgetDecision.APPROVED
    assert result.projected_loss == 50
    assert result.projected_operations == 3


def test_blocks_daily_loss_budget():
    result = RiskBudgetEvaluator().evaluate(RiskBudgetState(80, 1), RiskBudgetLimits(100, 5), 21)
    assert result.decision is BudgetDecision.BLOCKED
    assert result.projected_loss == 101


def test_blocks_operation_budget():
    result = RiskBudgetEvaluator().evaluate(RiskBudgetState(10, 5), RiskBudgetLimits(100, 5), 1)
    assert result.decision is BudgetDecision.BLOCKED
    assert result.projected_operations == 6


@pytest.mark.parametrize(
    "state,limits,loss",
    [
        (RiskBudgetState(-1, 0), RiskBudgetLimits(100, 5), 1),
        (RiskBudgetState(0, 0), RiskBudgetLimits(-1, 5), 1),
        (RiskBudgetState(0, 0), RiskBudgetLimits(100, 5), -1),
        (RiskBudgetState(0, -1), RiskBudgetLimits(100, 5), 1),
        (RiskBudgetState(0, 0), RiskBudgetLimits(100, 0), 1),
    ],
)
def test_invalid_budget_state_blocks(state, limits, loss):
    assert RiskBudgetEvaluator().evaluate(state, limits, loss).decision is BudgetDecision.BLOCKED


def test_non_finite_loss_blocks():
    result = RiskBudgetEvaluator().evaluate(RiskBudgetState(0, 0), RiskBudgetLimits(100, 5), float("inf"))
    assert result.decision is BudgetDecision.BLOCKED


def test_invalid_types_fail_closed():
    evaluator = RiskBudgetEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate(object(), RiskBudgetLimits(100, 5), 1)
    with pytest.raises(ValueError):
        evaluator.evaluate(RiskBudgetState(0, 0), object(), 1)
