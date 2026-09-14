from datetime import datetime, timezone

import pytest

from core.market_context import MarketContext, MarketContextResult
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState
from core.p47_automation_closure import AutomationClosureBoundary
from core.p49_outcome_reconciliation import ExternalOutcomeObservation, ReconciliationState
from integration.p139_post_demo_learning import PostDemoLearningBoundary


def _inputs():
    lifecycle = AutomationLifecycle("cycle-139", AutomationLifecycleState.COMPLETED)
    closure = AutomationClosureBoundary().close(
        lifecycle, closed_at=datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)
    )
    analysis = AnalysisResult(Signal.COMPRA, 90, "context", True, "EURUSD", "5m")
    context = MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=80,
        reason="Ambiente favorável com evidência contextual.",
        direction=MarketDirection.ALTA,
    )
    observation = ExternalOutcomeObservation("cycle-139", "WIN", 25.0)
    return closure, analysis, context, observation


def test_post_demo_boundary_closes_result_reconciliation_and_learning():
    closure, analysis, context, observation = _inputs()
    result = PostDemoLearningBoundary().process(
        closure=closure,
        observed_at=datetime(2026, 9, 14, 2, 1, tzinfo=timezone.utc),
        outcome="WIN",
        financial_result=25.0,
        external_observation=observation,
        analysis=analysis,
        market_context=context,
        note_id="note-139",
        what_happened="Resultado DEMO observado e reconciliado.",
        why_assessment="Os fatos externos correspondem ao resultado registrado.",
        evidence=("external-observation",),
        lessons=("preservar investigação antes de promover conhecimento",),
    )
    assert result.reconciliation.state is ReconciliationState.MATCHED
    assert result.snapshot.outcome == "WIN"
    assert result.handoff.learning_eligible is True
    assert result.execution_authorized is False


def test_mismatch_never_becomes_learning_eligible():
    closure, analysis, context, _ = _inputs()
    result = PostDemoLearningBoundary().process(
        closure=closure,
        observed_at=datetime(2026, 9, 14, 2, 1, tzinfo=timezone.utc),
        outcome="WIN",
        financial_result=25.0,
        external_observation=ExternalOutcomeObservation("cycle-139", "LOSS", -25.0),
        analysis=analysis,
        market_context=context,
        note_id="note-139-mismatch",
        what_happened="Resultado conflitante foi observado.",
        why_assessment="Os fatos externos não correspondem ao registro local.",
    )
    assert result.reconciliation.state is ReconciliationState.MISMATCHED
    assert result.handoff.learning_eligible is False
    assert result.handoff.evidence is None


def test_unknown_result_cannot_enter_learning():
    closure, analysis, context, _ = _inputs()
    with pytest.raises(ValueError, match="unknown operation outcome"):
        PostDemoLearningBoundary().process(
            closure=closure,
            observed_at=datetime(2026, 9, 14, 2, 1, tzinfo=timezone.utc),
            outcome="UNKNOWN",
            financial_result=None,
            external_observation=None,
            analysis=analysis,
            market_context=context,
            note_id="note-139-unknown",
            what_happened="Resultado ainda desconhecido.",
            why_assessment="Não há fatos suficientes para concluir.",
        )
