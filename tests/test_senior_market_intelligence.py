from __future__ import annotations

from core.p55_trusted_knowledge import TrustedKnowledge
from core.senior_market_intelligence import (
    DEFAULT_SENIOR_KNOWLEDGE_STANDARD,
    SeniorIntelligenceStatus,
    SeniorMarketIntelligenceBoundary,
)
from core.whole_graph_observation import WholeGraphObservationBoundary, WholeGraphStatus


def _graph(*, partial: bool = False):
    boundary = WholeGraphObservationBoundary()
    if partial:
        return boundary.audit(
            context_id="senior-cycle-partial",
            available_nodes=("history", "present", "volume"),
            observed_nodes=("history", "present"),
            gaps={"volume": "provider data unavailable"},
        )
    return boundary.audit(
        context_id="senior-cycle-ready",
        available_nodes=("history", "present", "structure", "liquidity"),
        observed_nodes=("history", "present", "structure", "liquidity"),
    )


def test_senior_standard_is_open_ended_and_covers_professional_context() -> None:
    assert DEFAULT_SENIOR_KNOWLEDGE_STANDARD.open_ended is True
    assert any("estrutura" in domain for domain in DEFAULT_SENIOR_KNOWLEDGE_STANDARD.domains)
    assert any("risco" in domain for domain in DEFAULT_SENIOR_KNOWLEDGE_STANDARD.domains)
    assert any("macro" in domain for domain in DEFAULT_SENIOR_KNOWLEDGE_STANDARD.domains)
    assert any("validação" in principle for principle in DEFAULT_SENIOR_KNOWLEDGE_STANDARD.principles)


def test_complete_graph_with_validated_knowledge_reaches_senior_ready() -> None:
    knowledge = TrustedKnowledge(
        knowledge_id="k-1",
        hypothesis_id="h-1",
        test_id="t-1",
        statement="knowledge validated in the existing learning pipeline",
        source_observation="observation-1",
    )
    result = SeniorMarketIntelligenceBoundary().assess(
        graph=_graph(),
        trusted_knowledge=(knowledge,),
    )

    assert result.status is SeniorIntelligenceStatus.READY
    assert result.knowledge_ids == ("builtin:senior-professional-baseline", "k-1")
    assert result.execution_authorized is False
    assert "todo o contexto materialmente disponibilizado foi contabilizado" in result.strengths


def test_partial_context_stays_partial_and_requires_reassessment() -> None:
    result = SeniorMarketIntelligenceBoundary().assess(
        graph=_graph(partial=True),
        trusted_knowledge=(),
    )

    assert result.status is SeniorIntelligenceStatus.PARTIAL
    assert result.gaps
    assert result.required_reassessment
    assert result.execution_authorized is False


def test_empty_external_knowledge_keeps_builtin_senior_baseline() -> None:
    result = SeniorMarketIntelligenceBoundary().assess(graph=_graph())

    assert result.status is SeniorIntelligenceStatus.READY
    assert result.knowledge_ids == ("builtin:senior-professional-baseline",)
    assert not any("nenhum conhecimento validado" in gap for gap in result.gaps)
    assert any("conhecimento profissional integrado de fábrica" in strength for strength in result.strengths)
    assert result.execution_authorized is False
