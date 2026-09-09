from pytest import raises

from core.p49_outcome_reconciliation import ReconciliationState
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from core.p51_learning_ingestion import LearningEligibility, LearningIngestionBoundary


def snapshot(state):
    return AutomationResultSnapshot("cycle-51", "COMPLETED", "WIN", 10.0, state)


def test_matched_snapshot_is_verified():
    record = LearningIngestionBoundary().ingest(snapshot(ReconciliationState.MATCHED))
    assert record.eligibility is LearningEligibility.VERIFIED


def test_unverified_snapshot_stays_unverified():
    record = LearningIngestionBoundary().ingest(snapshot(ReconciliationState.UNVERIFIED))
    assert record.eligibility is LearningEligibility.UNVERIFIED


def test_mismatched_snapshot_stays_mismatched():
    record = LearningIngestionBoundary().ingest(snapshot(ReconciliationState.MISMATCHED))
    assert record.eligibility is LearningEligibility.MISMATCHED


def test_invalid_snapshot_fails_closed():
    with raises(ValueError):
        LearningIngestionBoundary().ingest(None)


def test_record_is_immutable():
    record = LearningIngestionBoundary().ingest(snapshot(ReconciliationState.MATCHED))
    with raises(Exception):
        record.eligibility = LearningEligibility.MISMATCHED
