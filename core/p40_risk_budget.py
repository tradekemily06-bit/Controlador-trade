from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from enum import Enum


class BudgetDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RiskBudgetLimits:
    max_daily_loss: float
    max_operations: int


@dataclass(frozen=True)
class RiskBudgetState:
    accumulated_loss: float
    operations_count: int


@dataclass(frozen=True)
class RiskBudgetAssessment:
    decision: BudgetDecision
    projected_loss: float
    projected_operations: int
    reason: str


class RiskBudgetEvaluator:
    """Read-only daily risk budget check; it never records or executes operations."""

    def evaluate(
        self,
        state: RiskBudgetState,
        limits: RiskBudgetLimits,
        proposed_loss: float,
    ) -> RiskBudgetAssessment:
        if not isinstance(state, RiskBudgetState) or not isinstance(limits, RiskBudgetLimits):
            raise ValueError("risk budget input is invalid")
        values = (state.accumulated_loss, limits.max_daily_loss, proposed_loss)
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not isfinite(v) for v in values):
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "non-finite or invalid loss value")
        if not isinstance(state.operations_count, int) or isinstance(state.operations_count, bool) or state.operations_count < 0:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "operations count is invalid")
        if not isinstance(limits.max_operations, int) or isinstance(limits.max_operations, bool) or limits.max_operations <= 0:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "operation limit is invalid")
        if state.accumulated_loss < 0 or proposed_loss < 0 or limits.max_daily_loss < 0:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "loss values cannot be negative")

        projected_loss = state.accumulated_loss + proposed_loss
        projected_operations = state.operations_count + 1
        if projected_loss > limits.max_daily_loss:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, projected_loss, projected_operations, "daily loss budget exceeded")
        if projected_operations > limits.max_operations:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, projected_loss, projected_operations, "operation budget exceeded")
        return RiskBudgetAssessment(BudgetDecision.APPROVED, projected_loss, projected_operations, "risk budget satisfied")


def evaluate_risk_budget(
    state: RiskBudgetState,
    limits: RiskBudgetLimits,
    proposed_loss: float,
) -> RiskBudgetAssessment:
    return RiskBudgetEvaluator().evaluate(state, limits, proposed_loss)
