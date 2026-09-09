from datetime import datetime, timezone

from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.recovery_policy import RecoveryAction, RecoveryPolicy


def assessment(state):
    return RecoveryAssessment(state, None, (), (), "test")


def test_fresh_starts():
    assert RecoveryPolicy.plan(assessment(RecoveryState.FRESH)).action is RecoveryAction.START


def test_safe_resume():
    assert RecoveryPolicy.plan(assessment(RecoveryState.SAFE_TO_RESUME)).action is RecoveryAction.RESUME


def test_reconciliation_never_replays():
    assert RecoveryPolicy.plan(assessment(RecoveryState.REQUIRES_RECONCILIATION)).action is RecoveryAction.RECONCILE


def test_invalid_blocks():
    assert RecoveryPolicy.plan(assessment(RecoveryState.INVALID)).action is RecoveryAction.BLOCK
