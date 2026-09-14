from datetime import datetime, timedelta, timezone

from core.models import AnalysisResult, Signal
from core.senior_analysis_gate import SeniorAnalysisGate
from core.senior_context_orchestrator import SeniorContextInput, SeniorContextOrchestrator
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from data.models import Candle


def _candles():
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    return tuple(
        Candle(base + timedelta(minutes=i), 100 + i, 102 + i, 99 + i, 101 + i, 1000 + i)
        for i in range(5)
    )


def _context():
    candles = _candles()
    return SeniorContextOrchestrator().assess(
        SeniorContextInput(
            context_id="gate-test",
            candles=candles,
            available_nodes=("price", "structure", "volatility", "liquidity"),
            observed_nodes=("price", "structure", "volatility", "liquidity"),
            gaps={},
            relationships_reviewed=("price-structure", "structure-volatility", "price-liquidity"),
            risk_observations=(RiskObservation(RiskDomain.CAPITAL, "Capital observado.", True, ("account",)),),
            available_risk_domains=(RiskDomain.CAPITAL,),
        )
    )


def test_high_score_cannot_override_incomplete_context():
    context = SeniorContextOrchestrator().assess(
        SeniorContextInput(
            context_id="gate-incomplete",
            candles=_candles(),
            available_nodes=("price", "structure"),
            observed_nodes=("price", "structure"),
            gaps={},
            relationships_reviewed=("price-structure",),
            risk_observations=(),
            available_risk_domains=(RiskDomain.CAPITAL,),
        )
    )
    result = SeniorAnalysisGate().evaluate(
        analysis=AnalysisResult(Signal.COMPRA, 99, "score alto", True, "EURUSD", "5m"),
        senior_context=context,
    )
    assert result.signal is Signal.AGUARDAR
    assert result.score == 99


def test_supported_context_must_match_candidate_direction():
    result = SeniorAnalysisGate().evaluate(
        analysis=AnalysisResult(Signal.VENDA, 95, "score alto", True, "EURUSD", "5m"),
        senior_context=_context(),
    )
    assert result.signal is Signal.AGUARDAR


def test_supported_context_can_confirm_candidate_without_authorizing_execution():
    result = SeniorAnalysisGate().evaluate(
        analysis=AnalysisResult(Signal.COMPRA, 80, "score alto", True, "EURUSD", "5m"),
        senior_context=_context(),
    )
    assert result.signal is Signal.COMPRA
    assert result.confirmed is True
    assert "execução continua sujeita" in result.reason
