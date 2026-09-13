import pytest

from core.integrated_market_reading import IntegratedMarketReading, MarketObservation, ReadingStatus
from core.market_context import MarketContext, MarketContextResult
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.operation_learning_journal import OperationLearningJournal, OperationOutcome
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from core.p49_outcome_reconciliation import ReconciliationState
from core.p82_validation_result import ValidationResultStatus
from core.p83_validation_decision import ValidationDecisionStatus
from core.p128_learning_handoff import (
    IntegratedLearningValidationBoundary,
    OperationLearningHandoffBoundary,
)
from core.p77_context_audit import ContextAudit, ContextAuditStatus


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


def make_context_audit():
    return ContextAudit(
        context_id="context-128",
        handoff_id="handoff-128",
        archive_id="archive-128",
        status=ContextAuditStatus.AUDITABLE,
        rationale="Contexto completo e auditável.",
    )


def make_reading(status=ReadingStatus.SUPPORTED):
    return IntegratedMarketReading(
        status=status,
        observations=(
            MarketObservation("structure-1", "structure", "Estrutura favorece o deslocamento.", "BUY", 0.8, "market_structure"),
            MarketObservation("context-1", "volatility", "Volatilidade compatível com investigação.", "NEUTRAL", 0.7, "market_environment"),
        ),
        supporting=("structure-1",),
        contradicting=(),
        conflicts=(),
        possible_false_breakout=False,
        unanswered_questions=("O que sustenta a relação observada?",),
    )


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
            snapshot=snapshot, note=bad_note, analysis=analysis, market_context=context
        )


def test_supported_integrated_reading_enters_existing_validation_path():
    candidate = IntegratedLearningValidationBoundary().prepare(
        reading=make_reading(), context_audit=make_context_audit(), cycle_id="cycle-128",
        hypothesis_id="hyp-128", admission_id="admission-128", test_id="test-128", run_id="run-128",
    )
    assert candidate.hypothesis is not None
    assert candidate.hypothesis.hypothesis_id == "hyp-128"
    assert candidate.admission is not None
    assert candidate.specification is not None
    assert candidate.validation_run is not None
    assert candidate.validation_result is None
    assert candidate.validation_decision is None
    assert candidate.specification.hypothesis_id == "hyp-128"
    assert candidate.validation_run.test_id == "test-128"
    assert candidate.validation_run.admission_id == "admission-128"
    assert candidate.source_observation_ids == ("structure-1", "context-1")
    assert candidate.unanswered_questions
    assert candidate.execution_authorized is False


def test_supported_candidate_closes_through_p82_and_p83_without_execution_authority():
    boundary = IntegratedLearningValidationBoundary()
    candidate = boundary.prepare(
        reading=make_reading(), context_audit=make_context_audit(), cycle_id="cycle-close",
        hypothesis_id="hyp-close", admission_id="admission-close", test_id="test-close", run_id="run-close",
    )
    concluded = boundary.conclude(
        candidate,
        result_id="result-close",
        result_status=ValidationResultStatus.POSITIVE,
        result_rationale="Evidência positiva dentro dos critérios do teste.",
        decision_id="decision-close",
        decision_status=ValidationDecisionStatus.VALIDATED,
        decision_rationale="Resultado positivo; conhecimento pode seguir para a memória/validação superior.",
    )
    assert concluded.validation_result is not None
    assert concluded.validation_result.result_id == "result-close"
    assert concluded.validation_decision is not None
    assert concluded.validation_decision.status is ValidationDecisionStatus.VALIDATED
    assert concluded.execution_authorized is False


def test_invalid_p82_p83_pair_is_rejected():
    boundary = IntegratedLearningValidationBoundary()
    candidate = boundary.prepare(
        reading=make_reading(), context_audit=make_context_audit(), cycle_id="cycle-invalid",
        hypothesis_id="hyp-invalid", admission_id="admission-invalid", test_id="test-invalid", run_id="run-invalid",
    )
    with pytest.raises(ValueError, match="only positive"):
        boundary.conclude(
            candidate,
            result_id="result-invalid",
            result_status=ValidationResultStatus.NEGATIVE,
            result_rationale="Resultado negativo.",
            decision_id="decision-invalid",
            decision_status=ValidationDecisionStatus.VALIDATED,
            decision_rationale="Tentativa inválida de validar resultado negativo.",
        )


def test_conflicting_reading_remains_investigation_only():
    candidate = IntegratedLearningValidationBoundary().prepare(
        reading=make_reading(ReadingStatus.CONFLICTING), context_audit=make_context_audit(), cycle_id="cycle-conflict",
        hypothesis_id="hyp-conflict", admission_id="admission-conflict", test_id="test-conflict", run_id="run-conflict",
    )
    assert candidate.hypothesis is None
    assert candidate.admission is None
    assert candidate.specification is None
    assert candidate.validation_run is None
    assert candidate.execution_authorized is False


def test_insufficient_reading_cannot_be_promoted():
    candidate = IntegratedLearningValidationBoundary().prepare(
        reading=make_reading(ReadingStatus.INSUFFICIENT), context_audit=make_context_audit(), cycle_id="cycle-insufficient",
        hypothesis_id="hyp-insufficient", admission_id="admission-insufficient", test_id="test-insufficient", run_id="run-insufficient",
    )
    assert candidate.hypothesis is None
    assert candidate.unanswered_questions
    assert candidate.execution_authorized is False
