from core.operation_learning_journal import (
    InvestigationQuestion,
    OperationLearningJournal,
    OperationOutcome,
)


def test_win_and_loss_both_create_learning_records():
    journal = OperationLearningJournal()
    for outcome in (OperationOutcome.WIN, OperationOutcome.LOSS):
        note = journal.create_note(
            note_id=f"n-{outcome.value.lower()}",
            outcome=outcome,
            what_happened="resultado observado",
            why_assessment="avaliação inicial a confirmar",
            market_context="contexto observado",
            evidence=("evidência factual",),
            questions=journal.default_questions(outcome),
            lessons=("comparar com casos anteriores",),
        )
        assert note.outcome is outcome
        assert len(note.questions) >= 5
        assert note.lessons


def test_questions_cover_what_why_context_evidence_and_reassessment():
    questions = OperationLearningJournal().default_questions(OperationOutcome.LOSS)
    assert {q.category for q in questions} == {"what", "why", "context", "evidence", "reassessment"}
    assert all(isinstance(q, InvestigationQuestion) for q in questions)


def test_note_requires_factual_description_and_context():
    journal = OperationLearningJournal()
    try:
        journal.create_note(
            note_id="n1", outcome=OperationOutcome.WIN,
            what_happened="", why_assessment="ok", market_context="ok"
        )
    except ValueError as exc:
        assert "what_happened" in str(exc)
    else:
        raise AssertionError("empty observation must fail closed")
