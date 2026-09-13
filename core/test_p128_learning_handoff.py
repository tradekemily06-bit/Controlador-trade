import pytest

from core.market_context import MarketContext, MarketContextResult
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.operation_learning_journal import OperationLearningJournal, OperationOutcome
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from core.p49_outcome_reconciliation import ReconciliationState
from core.p128_learning_handoff import OperationLearningHandoffBoundary


def make_inputs(reconciliation_state=ReconciliationState.MATCHED):
    snapshot = AutomationResultSnapshot(
        cycle_id="cycle-128",
        terminal_state="CLOSED",
        outcome="WIN",
        financial_result=25.0,
        reconciliation_state=reconciliation_state,
    )
    note = OperationLearningJournal().create_note(
        note_id="note-128",
        outcome=OperationOutcome.WIN,
        what_happened="A operação venceu após a leitura e confirmação do contexto.",
        why_assessment="A leitura teve suporte no contexto observado.",
        market_context="Tendência, volatilidade e liquidez foram avaliadas em conjunto.",
        evidence=("resultado reconciliado",),
        questions=OperationLearningJournal().default_questions(OperationOutcome.WIN),
        lessons=("Reavaliar a leitura quando novas evidências surgirem.",),
    )
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=82,
        reason="Leitura contextual confirmada.",
        confirmed=True,
        symbol="TEST",
        timeframe="5m",
    )
    context = MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=78,
        reason="Ambiente favorável.",
        direction=MarketDirection.ALTA,
    )
    return snapshot, note, analysis, context


def test_handoff_keeps_result_reading_and_context_together():
    snapshot, note, analysis, context = make_inputs()
    handoff = OperationLearningHandoffBoundary().build(
        snapshot=snapshot, note=note, analysis=analysis, market_context=context
    )

    assert handoff.cycle_id == "cycle-128"
    assert handoff.note is note
    assert handoff.analysis is analysis
    assert handoff.market_context is context
    assert handoff.learning_eligible is True
    assert handoff.evidence is not None
    assert handoff.execution_authorized is False


def test_unverified_result_cannot_become_learning_evidence():
    snapshot, note, analysis, context = make_inputs(ReconciliationState.UNVERIFIED)
    handoff = OperationLearningHandoffBoundary().build(
        snapshot=snapshot, note=note, analysis=analysis, market_context=context
    )

    assert handoff.evidence is None
    assert handoff.learning_eligible is False
    assert handoff.execution_authorized is False


def test_outcome_mismatch_is_rejected():
    snapshot, _, analysis, context = make_inputs()
    bad_note = OperationLearningJournal().create_note(
        note_id="bad-note",
        outcome=OperationOutcome.LOSS,
        what_happened="Resultado divergente.",
        why_assessment="Não concluído.",
        market_context="Contexto registrado.",
    )

    with pytest.raises(ValueError, match="outcome"):
        OperationLearningHandoffBoundary().build(
            snapshot=snapshot,
            note=bad_note,
            analysis=analysis,
            market_context=context,
        )
