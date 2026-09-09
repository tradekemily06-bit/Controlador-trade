from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RiskLimits:
    max_order_amount: float
    max_total_exposure: float


@dataclass(frozen=True)
class RiskProposal:
    order_amount: float
    current_exposure: float


@dataclass(frozen=True)
class RiskAssessment:
    decision: RiskDecision
    projected_exposure: float
    reason: str


class PreTradeRiskEvaluator:
    """Read-only risk boundary; it never submits or mutates an operation."""

    def evaluate(self, proposal: RiskProposal, limits: RiskLimits) -> RiskAssessment:
        if not isinstance(proposal, RiskProposal):
            raise ValueError("proposal is invalid")
        if not isinstance(limits, RiskLimits):
            raise ValueError("limits are invalid")

        values = (
            proposal.order_amount,
            proposal.current_exposure,
            limits.max_order_amount,
            limits.max_total_exposure,
        )
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) for value in values):
            return RiskAssessment(RiskDecision.BLOCKED, 0.0, "non-finite or invalid risk value")
        if proposal.order_amount <= 0:
            return RiskAssessment(RiskDecision.BLOCKED, proposal.current_exposure, "order amount must be positive")
        if proposal.current_exposure < 0:
            return RiskAssessment(RiskDecision.BLOCKED, 0.0, "current exposure cannot be negative")
        if limits.max_order_amount <= 0 or limits.max_total_exposure < 0:
            return RiskAssessment(RiskDecision.BLOCKED, 0.0, "risk limits are invalid")

        projected = proposal.current_exposure + proposal.order_amount
        if proposal.order_amount > limits.max_order_amount:
            return RiskAssessment(RiskDecision.BLOCKED, projected, "order amount exceeds limit")
        if projected > limits.max_total_exposure:
            return RiskAssessment(RiskDecision.BLOCKED, projected, "projected exposure exceeds limit")
        return RiskAssessment(RiskDecision.APPROVED, projected, "risk limits satisfied")


def evaluate_pretrade_risk(proposal: RiskProposal, limits: RiskLimits) -> RiskAssessment:
    return PreTradeRiskEvaluator().evaluate(proposal, limits)
