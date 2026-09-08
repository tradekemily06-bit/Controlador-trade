from core.decision_engine import DecisionResult, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.market_context import MarketContext, MarketContextResult, MarketDirection
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.signal_quality import SignalLevel, SignalQuality


def make_analysis() -> AnalysisResult:
    return AnalysisResult(
        signal=Signal.COMPRA,
        score=90.0,
        reason="Sinal confirmado.",
        confirmed=True,
        symbol="TEST",
        timeframe="5m",
    )


def make_quality() -> SignalQuality:
    return SignalQuality(
        score=80.0,
        level=SignalLevel.FORTE,
        actionable=True,
    )


def make_context() -> MarketContextResult:
    return MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=90.0,
        direction=MarketDirection.ALTA,
        reason="Contexto favorável.",
    )


def make_state() -> OperationalState:
    return OperationalState(
        balance=1000.0,
        realized_pnl=0.0,
        trades_today=2,
        consecutive_losses=1,
        market_open=True,
    )


def test_snapshot_preserves_all_decision_inputs_and_result():
    snapshot = DecisionSnapshot.from_results(
        analysis=make_analysis(),
        quality=make_quality(),
        decision=DecisionResult(
            decision=FinalDecision.EXECUTAR,
            signal=Signal.COMPRA,
            reason="Todos os requisitos aprovados.",
        ),
        market_context=make_context(),
        operational_state=make_state(),
    )

    assert snapshot.signal == "COMPRA"
    assert snapshot.analysis_score == 90.0
    assert snapshot.confirmed is True
    assert snapshot.quality_score == 80.0
    assert snapshot.quality_level == "FORTE"
    assert snapshot.actionable is True
    assert snapshot.decision == FinalDecision.EXECUTAR
    assert snapshot.market_context == "FAVORAVEL"
    assert snapshot.market_direction == "ALTA"
    assert snapshot.market_score == 90.0
    assert snapshot.operational_state_available is True
    assert snapshot.trades_today == 2
    assert snapshot.consecutive_losses == 1
    assert snapshot.symbol == "TEST"
    assert snapshot.timeframe == "5m"


def test_snapshot_is_immutable():
    snapshot = DecisionSnapshot.from_results(
        analysis=make_analysis(),
        quality=make_quality(),
        decision=DecisionResult(
            decision=FinalDecision.EXECUTAR,
            signal=Signal.COMPRA,
            reason="Aprovado.",
        ),
        market_context=make_context(),
        operational_state=make_state(),
    )

    try:
        snapshot.decision = FinalDecision.BLOQUEAR
    except AttributeError:
        pass
    else:
        raise AssertionError("DecisionSnapshot deve ser imutável.")


def test_snapshot_handles_missing_context_and_operational_state():
    snapshot = DecisionSnapshot.from_results(
        analysis=make_analysis(),
        quality=make_quality(),
        decision=DecisionResult(
            decision=FinalDecision.AGUARDAR,
            signal=Signal.COMPRA,
            reason="Dados indisponíveis.",
        ),
        market_context=None,
        operational_state=None,
    )

    assert snapshot.market_context is None
    assert snapshot.market_direction is None
    assert snapshot.market_score is None
    assert snapshot.operational_state_available is False
    assert snapshot.trades_today is None
    assert snapshot.consecutive_losses is None


def test_snapshot_as_dict_and_explain_are_consistent():
    snapshot = DecisionSnapshot.from_results(
        analysis=make_analysis(),
        quality=make_quality(),
        decision=DecisionResult(
            decision=FinalDecision.EXECUTAR,
            signal=Signal.COMPRA,
            reason="Todos os requisitos aprovados.",
        ),
        market_context=make_context(),
        operational_state=make_state(),
    )

    data = snapshot.as_dict()
    explanation = snapshot.explain()

    assert data["signal"] == "COMPRA"
    assert data["decision"] == FinalDecision.EXECUTAR
    assert data["quality_level"] == "FORTE"
    assert "Sinal=COMPRA" in explanation
    assert "qualidade=FORTE" in explanation
    assert "decisão=EXECUTAR" in explanation
    assert "contexto=FAVORAVEL" in explanation
