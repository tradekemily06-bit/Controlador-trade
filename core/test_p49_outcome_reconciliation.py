from datetime import datetime, timezone

import pytest

from core.p48_automation_outcome import AutomationOutcome
from core.p49_outcome_reconciliation import (
    ExternalOutcomeObservation,
    OutcomeReconciliationBoundary,
    ReconciliationState,
)
from core.p46_automation_lifecycle import AutomationLifecycleState


def outcome():
    return AutomationOutcome("cycle-49", AutomationLifecycleState.COMPLETED, datetime(2026, 9, 9, 12, tzinfo=timezone.utc), "WIN", 10.0)


def test_matching_facts_are_matched():
    result = OutcomeReconciliationBoundary().reconcile(
        outcome(), ExternalOutcomeObservation("cycle-49", "WIN", 10.0)
    )
    assert result.state is ReconciliationState.MATCHED


def test_missing_observation_is_unverified():
    result = OutcomeReconciliationBoundary().reconcile(outcome(), None)
    assert result.state is ReconciliationState.UNVERIFIED


def test_mismatch_is_explicit_and_not_corrected():
    result = OutcomeReconciliationBoundary().reconcile(
        outcome(), ExternalOutcomeObservation("cycle-49", "LOSS", -10.0)
    )
    assert result.state is ReconciliationState.MISMATCHED
    assert "mismatch" in result.reason


def test_cycle_mismatch_is_detected():
    result = OutcomeReconciliationBoundary().reconcile(
        outcome(), ExternalOutcomeObservation("other-cycle", "WIN", 10.0)
    )
    assert result.state is ReconciliationState.MISMATCHED


def test_invalid_observation_fails_closed():
    with pytest.raises(ValueError):
        OutcomeReconciliationBoundary().reconcile(outcome(), "invalid")


def test_reconciliation_is_immutable():
    result = OutcomeReconciliationBoundary().reconcile(outcome(), None)
    with pytest.raises(Exception):
        result.state = ReconciliationState.MATCHED
