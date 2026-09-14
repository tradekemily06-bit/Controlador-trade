import pytest

from core.market_context import MarketContext, MarketContextResult
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.p49_outcome_reconciliation import ReconciliationState
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from integration.p138_result_learning_bridge import ResultLearningBridge


def _snapshot(outcome="WIN"):
    return AutomationResultSnapshot(
        cycle_id="cycle-138",
        terminal_state="COMPLETED",
        outcome=outcome,
        financial_result=25.0 if outcome == "WIN" else -25.0,
        reconciliation_state=ReconciliationState.MATCHED,
    )


def _analysis():
    return AnalysisResult(Signal.COMPRA, 90, "context", True, "EURUSD", "5m")


def _context():
    return MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=80,
        reason="Ambiente favorável com evidência contextual.",
        direction=MarketDirection.ALTA,
    )


def test_bridge_builds_reconciled_learning_handoff_without_execution_authority():
    handoff = ResultLearningBridge().build(
        snapshot=_snapshot(),
        analysis=_analysis(),
        market_context=_context(),
        note_id="note-138",
        what_happened="Resultado reconciliado após execução DEMO.",
        why_assessment="A leitura foi sustentada pelo contexto observado.",
        evidence=("reconciled-result",),
        lessons=("manter investigação antes de promover conhecimento",),
    )
    assert handoff.cycle_id == "cycle-138"
    assert handoff.note.outcome.value == "WIN"
    assert handoff.learning_eligible is True
    assert handoff.evidence is not None
    assert handoff.execution_authorized is False


def test_bridge_rejects_unknown_outcome():
    with pytest.raises(ValueError, match="unknown operation outcome"):
        ResultLearningBridge().build(
            snapshot=_snapshot("UNKNOWN"),
            analysis=_analysis(),
            market_context=_context(),
            note_id="note-unknown",
            what_happened="Resultado não reconciliado.",
            why_assessment="Não há base para aprender ainda.",
        )
