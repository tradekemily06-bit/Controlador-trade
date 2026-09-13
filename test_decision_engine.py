from core.models import AnalysisResult, Signal
from core.risk_manager import RiskManager
from core.decision_engine import DecisionEngine, FinalDecision
from core.operational_state import OperationalState
from core.market_context import MarketContext, MarketContextResult, MarketDirection
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment


def operational_state(*, realized_pnl=0, trades_today=0, consecutive_losses=0):
    return OperationalState(
        realized_pnl=realized_pnl,
        trades_today=trades_today,
        consecutive_losses=consecutive_losses,
    )


def favorable_context(direction):
    return MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=85,
        reason="Ambiente favorável.",
        direction=direction,
    )


def senior_context(quality=SeniorContextQuality.COMPLETE, *, execution_authorized=False):
    senior_risk = SeniorRiskAssessment(
        status=RiskKnowledgeStatus.ASSESSED,
        observations=(),
        material_risks=(),
        unknowns=(),
        questions=(),
        reassessment_triggers=(),
        execution_authorized=False,
    )
    return SeniorContextCycle(
        cycle_id="test-cycle",
        whole_graph=None,
        temporal_context=None,
        market_reading=None,
        senior_assessment=None,
        risk_assessment=senior_risk,
        validated_knowledge_ids=(),
        unresolved_questions=(),
        quality=quality,
        execution_authorized=execution_authorized,
    )


def test_nao_executa_sem_contexto_senior():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=100, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(),
    )
    assert result.decision == FinalDecision.AGUARDAR
    assert "Contexto sênior obrigatório" in result.reason


def test_executa_compra_com_contexto_senior_completo():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=80, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(realized_pnl=-20),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.EXECUTAR
    assert result.signal == Signal.COMPRA


def test_executa_venda_com_contexto_senior_completo():
    analysis = AnalysisResult(signal=Signal.VENDA, score=20, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.BAIXA),
        operational_state=operational_state(realized_pnl=-20),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.EXECUTAR
    assert result.signal == Signal.VENDA


def test_bloqueia_sinal_por_risco():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=90, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(realized_pnl=-100),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_aguarda_quando_nao_existe_sinal():
    analysis = AnalysisResult(signal=Signal.AGUARDAR, score=50, reason="Score insuficiente.", confirmed=True)
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(analysis=analysis)
    assert result.decision == FinalDecision.AGUARDAR


def test_bloqueia_por_limite_de_operacoes():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=85, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager(max_operations=5)).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(trades_today=5),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_bloqueia_por_perdas_consecutivas():
    analysis = AnalysisResult(signal=Signal.VENDA, score=15, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager(max_consecutive_losses=3)).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.BAIXA),
        operational_state=operational_state(consecutive_losses=3),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_aguarda_compra_com_contexto_favoravel_na_baixa():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=80, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.BAIXA),
        operational_state=operational_state(),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_aguarda_venda_com_contexto_favoravel_na_alta():
    analysis = AnalysisResult(signal=Signal.VENDA, score=20, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_aguarda_com_contexto_neutro():
    context = MarketContextResult(context=MarketContext.NEUTRO, score=50, reason="Ambiente neutro.", direction=MarketDirection.ALTA)
    analysis = AnalysisResult(signal=Signal.COMPRA, score=80, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=operational_state(),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_aguarda_com_contexto_desfavoravel():
    context = MarketContextResult(context=MarketContext.DESFAVORAVEL, score=20, reason="Ambiente desfavorável.", direction=MarketDirection.BAIXA)
    analysis = AnalysisResult(signal=Signal.VENDA, score=20, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=operational_state(),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_contexto_senior_requer_reavaliacao():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=90, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(),
        senior_context=senior_context(SeniorContextQuality.REASSESS),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_contexto_senior_completo_nao_substitui_risco_operacional():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=90, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(realized_pnl=-100),
        senior_context=senior_context(),
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_contexto_senior_nunca_pode_conceder_autorizacao():
    analysis = AnalysisResult(signal=Signal.COMPRA, score=90, reason="Score forte.", confirmed=True)
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_context(MarketDirection.ALTA),
        operational_state=operational_state(),
        senior_context=senior_context(execution_authorized=True),
    )
    assert result.decision == FinalDecision.BLOQUEAR
