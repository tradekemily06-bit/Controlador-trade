import pytest

from core.operation_learning_journal import LearningIdentityConflict, OperationLearningJournal, OperationOutcome
from core.p49_outcome_reconciliation import ReconciliationState
from core.p50_automation_result_snapshot import AutomationResultSnapshot


def snapshot(ids=("deal-1",), financial=10.0):
    return AutomationResultSnapshot(
        cycle_id="cycle-idempotent",
        terminal_state="COMPLETED",
        outcome="WIN",
        financial_result=financial,
        reconciliation_state=ReconciliationState.MATCHED,
        source="TEST",
        external_reference="close-1",
        external_container_id="position-1",
        external_result_ids=ids,
    )


def note(journal, note_id):
    return journal.create_note(
        note_id=note_id,
        outcome=OperationOutcome.WIN,
        what_happened="resultado confirmado",
        why_assessment="evidência externa",
        market_context="contexto capturado",
        evidence=("deal",),
        questions=journal.default_questions(OperationOutcome.WIN),
    )


def test_verified_learning_survives_restart_and_deduplicates(tmp_path):
    path = tmp_path / "learning.sqlite3"
    first = OperationLearningJournal(str(path))
    created = note(first, "note-1")
    key = first.verified_dedupe_key(snapshot())
    identity = first.verified_evidence_identity(snapshot())
    assert first.persist_verified_note(created, dedupe_key=key, evidence_identity=identity) is True

    second = OperationLearningJournal(str(path))
    duplicate = note(second, "note-2")
    assert second.persist_verified_note(duplicate, dedupe_key=key, evidence_identity=identity) is True
    assert second.verified_note(dedupe_key=key).note_id == "note-1"


def test_verified_learning_accepts_delayed_external_history_growth_as_same_record(tmp_path):
    path = tmp_path / "learning.sqlite3"
    journal = OperationLearningJournal(str(path))
    first = snapshot(("deal-1",), 10.0)
    second = snapshot(("deal-1", "deal-2"), 12.0)
    created = note(journal, "note-1")
    assert journal.persist_verified_note(
        created,
        dedupe_key=journal.verified_dedupe_key(first),
        evidence_identity=journal.verified_evidence_identity(first),
    )
    updated = note(journal, "note-2")
    assert journal.persist_verified_note(
        updated,
        dedupe_key=journal.verified_dedupe_key(second),
        evidence_identity=journal.verified_evidence_identity(second),
    )
    assert journal.verified_note(dedupe_key="cycle:cycle-idempotent").note_id == "note-1"


def test_conflicting_verified_identity_fails_closed(tmp_path):
    journal = OperationLearningJournal(str(tmp_path / "learning.sqlite3"))
    first = snapshot(("deal-1",), 10.0)
    created = note(journal, "note-1")
    journal.persist_verified_note(
        created,
        dedupe_key=journal.verified_dedupe_key(first),
        evidence_identity=journal.verified_evidence_identity(first),
    )
    conflict = snapshot(("deal-99",), 10.0)
    with pytest.raises(LearningIdentityConflict):
        journal.persist_verified_note(
            note(journal, "note-2"),
            dedupe_key=journal.verified_dedupe_key(conflict),
            evidence_identity=journal.verified_evidence_identity(conflict),
        )
