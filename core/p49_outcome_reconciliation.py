from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p48_automation_outcome import AutomationOutcome


class ReconciliationState(str, Enum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class ExternalOutcomeObservation:
    cycle_id: str
    outcome: str
    financial_result: float | None


@dataclass(frozen=True)
class OutcomeReconciliation:
    cycle_id: str
    state: ReconciliationState
    reason: str


class OutcomeReconciliationBoundary:
    """Compares explicit facts only; it never fetches or mutates external state."""

    def reconcile(
        self,
        outcome: AutomationOutcome,
        observation: ExternalOutcomeObservation | None,
    ) -> OutcomeReconciliation:
        if not isinstance(outcome, AutomationOutcome):
            raise ValueError("invalid automation outcome")
        if not isinstance(outcome.cycle_id, str) or not outcome.cycle_id.strip():
            raise ValueError("cycle_id is required")
        if observation is None:
            return OutcomeReconciliation(outcome.cycle_id, ReconciliationState.UNVERIFIED, "external observation is absent")
        if not isinstance(observation, ExternalOutcomeObservation):
            raise ValueError("invalid external outcome observation")
        if not isinstance(observation.cycle_id, str) or not observation.cycle_id.strip():
            raise ValueError("external cycle_id is required")
        if observation.cycle_id != outcome.cycle_id:
            return OutcomeReconciliation(outcome.cycle_id, ReconciliationState.MISMATCHED, "cycle_id mismatch")
        if observation.outcome != outcome.outcome:
            return OutcomeReconciliation(outcome.cycle_id, ReconciliationState.MISMATCHED, "outcome mismatch")
        if observation.financial_result != outcome.financial_result:
            return OutcomeReconciliation(outcome.cycle_id, ReconciliationState.MISMATCHED, "financial_result mismatch")
        return OutcomeReconciliation(outcome.cycle_id, ReconciliationState.MATCHED, "explicit facts match")
