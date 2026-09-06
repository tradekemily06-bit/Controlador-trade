from core.models import AnalysisResult, Signal
from core.risk_manager import RiskManager
from core.decision_engine import DecisionEngine, FinalDecision


def test_executa_compra_com_risco_aprovado():
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=80,
        reason="Score forte.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        daily_result=-20,
    )
    assert result.decision == FinalDecision.EXECUTAR
    assert result.signal == Signal.COMPRA


def test_executa_venda_com_risco_aprovado():
    analysis = AnalysisResult(
        signal=Signal.VENDA,
        score=20,
        reason="Score forte.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        daily_result=-20,
    )
    assert result.decision == FinalDecision.EXECUTAR
    assert result.signal == Signal.VENDA


def test_bloqueia_sinal_por_risco():
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=90,
        reason="Score forte.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        daily_result=-100,
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_aguarda_quando_nao_existe_sinal():
    analysis = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=50,
        reason="Score insuficiente.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_bloqueia_por_limite_de_operacoes():
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=85,
        reason="Score forte.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(max_operations=5)).evaluate(
        analysis=analysis,
        operations_count=5,
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_bloqueia_por_perdas_consecutivas():
    analysis = AnalysisResult(
        signal=Signal.VENDA,
        score=15,
        reason="Score forte.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(max_consecutive_losses=3)).evaluate(
        analysis=analysis,
        consecutive_losses=3,
    )
    assert result.decision == FinalDecision.BLOQUEAR
