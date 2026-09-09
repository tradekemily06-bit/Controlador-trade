from datetime import datetime, timezone

import pytest

from core.p46_automation_lifecycle import AutomationLifecycleState
from core.p47_automation_closure import AutomationClosure
from core.p48_automation_outcome import AutomationOutcome
from core.p49_outcome_reconciliation import OutcomeReconciliation, ReconciliationState
from core.p50_automation_result_snapshot import AutomationResultSnapshotBoundary


def artifacts():
    closure = AutomationClosure("cycle-50", AutomationLifecycleState.COMPLETED, datetime(2026, 9, 9, 12, tzinfo=timezone.utc))
    outcome = AutomationOutcome("cycle-50", AutomationLifecycleState.COMPLETED, datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc), "WIN", 15.0)
    reconciliation = OutcomeReconciliation("cycle-50", ReconciliationState.MATCHED, "explicit facts match")
    return closure, outcome, reconciliation


def test_composes_integrated_snapshot():
    snapshot = AutomationResultSnapshotBoundary().compose(*artifacts())
    assert snapshot.cycle_id == "cycle-50"
    assert snapshot.terminal_state == "COMPLETED"
    assert snapshot.outcome == "WIN"
    assert snapshot.financial_result == 15.0
    assert snapshot.reconciliation_state is ReconciliationState.MATCHED


def test_rejects_mixed_cycles():
    closure, outcome, reconciliation = artifacts()
    mismatched = OutcomeReconciliation("other-cycle", ReconciliationState.MATCHED, "explicit facts match")
    with pytest.raises(ValueError):
        AutomationResultSnapshotBoundary().compose(closure, outcome, mismatched)


def test_rejects_terminal_state_mismatch():
    closure, outcome, reconciliation = artifacts()
    mismatched = AutomationOutcome("cycle-50", AutomationLifecycleState.BLOCKED, outcome.observed_at, "UNKNOWN", None)
    with pytest.raises(ValueError):
        AutomationResultSnapshotBoundary().compose(closure, mismatched, reconciliation)


def test_unknown_cannot_be_matched():
    closure, _, reconciliation = artifacts()
    unknown = AutomationOutcome("cycle-50", AutomationLifecycleState.COMPLETED, datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc), "UNKNOWN", None)
    with pytest.raises(ValueError):
        AutomationResultSnapshotBoundary().compose(closure, unknown, reconciliation)


def test_snapshot_is_immutable():
    snapshot = AutomationResultSnapshotBoundary().compose(*artifacts())
    with pytest.raises(Exception):
        snapshot.outcome = "LOSS"
