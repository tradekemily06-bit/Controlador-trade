import pytest

from core.p49_outcome_reconciliation import ReconciliationState
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from core.p51_learning_ingestion import LearningEligibility, LearningIngestionBoundary
from core.p52_learning_evidence import LearningEvidenceBoundary


def record(state):
    return LearningIngestionBoundary().ingest(
        AutomationResultSnapshot("cycle-52", "COMPLETED", "WIN", 8.0, state)
    )


def test_verified_record_becomes_factual_evidence():
    evidence = LearningEvidenceBoundary().build(record(ReconciliationState.MATCHED))
    assert evidence.factual is True
    assert evidence.cycle_id == "cycle-52"
    assert evidence.outcome == "WIN"


@pytest.mark.parametrize("state", [ReconciliationState.UNVERIFIED, ReconciliationState.MISMATCHED])
def test_untrusted_records_are_rejected(state):
    with pytest.raises(ValueError):
        LearningEvidenceBoundary().build(record(state))


def test_invalid_record_fails_closed():
    with pytest.raises(ValueError):
        LearningEvidenceBoundary().build(None)


def test_evidence_is_immutable():
    evidence = LearningEvidenceBoundary().build(record(ReconciliationState.MATCHED))
    with pytest.raises(Exception):
        evidence.outcome = "LOSS"
