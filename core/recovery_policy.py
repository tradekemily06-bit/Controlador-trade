from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.recovery_coordinator import RecoveryAssessment, RecoveryState


class RecoveryAction(str, Enum):
    START = "START"
    RESUME = "RESUME"
    RECONCILE = "RECONCILE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class RecoveryPlan:
    action: RecoveryAction
    reason: str


class RecoveryPolicy:
    """Converts recovery assessment into an explicit, non-executing safety plan."""

    @staticmethod
    def plan(assessment: RecoveryAssessment) -> RecoveryPlan:
        if not isinstance(assessment, RecoveryAssessment):
            raise ValueError("assessment inválida.")
        if assessment.state is RecoveryState.FRESH:
            return RecoveryPlan(RecoveryAction.START, assessment.message)
        if assessment.state is RecoveryState.SAFE_TO_RESUME:
            return RecoveryPlan(RecoveryAction.RESUME, assessment.message)
        if assessment.state is RecoveryState.REQUIRES_RECONCILIATION:
            return RecoveryPlan(RecoveryAction.RECONCILE, assessment.message)
        return RecoveryPlan(RecoveryAction.BLOCK, assessment.message)
