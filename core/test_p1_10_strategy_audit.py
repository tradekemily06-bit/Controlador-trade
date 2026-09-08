from core.decision_engine import DecisionEngine, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.market_context import MarketContext, MarketContextResult
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.risk_manager import RiskManager
from core.signal_quality import SignalLevel, SignalQualityEvaluator
from execution.demo_flow import DemoFlow
from execution.paper import PaperExecutor
from audit.events import AuditEventType, AuditLogger


def make_analysis(signal=Signal.COMPRA, score=100.0, confirmed=True):
    return AnalysisResult(
        signal=signal,
        score=score,
        reason="Teste de auditoria P1.10.",
        confirmed=confirmed,
        symbol="BTCUSD",
        timeframe="5m",
    )


def make_state(*, trades_today=0, consecutive_losses=0, realized_pnl=0.0):
    return OperationalState(
        realized_pnl=realized_pnl,
        trades_today=trades_today,
        consecutive_losses=consecutive_losses,
    )


def make_context(direction=MarketDirection.ALTA, score=100.0):
    return MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=score,
        reason="Contexto favorável para teste.",
        direction=direction,
    )


def test_full_executable_path_reaches_execute():
    analysis = make_analysis()
    state = make_state()
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=make_context(),
        operational_state=state,
    )

    assert decision.decision == FinalDecision.EXECUTAR
    assert decision.signal == Signal.COMPRA


def test_missing_operational_state_never_executes():
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=make_analysis(),
        market_context=make_context(),
        operational_state=None,
    )

    assert decision.decision == FinalDecision.AGUARDAR
    assert "Estado operacional" in decision.reason


def test_missing_market_context_never_executes():
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=make_analysis(),
        market_context=None,
        operational_state=make_state(),
    )

    assert decision.decision == FinalDecision.AGUARDAR
    assert "Contexto de mercado" in decision.reason


def test_incompatible_direction_never_executes():
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=make_analysis(signal=Signal.COMPRA),
        market_context=make_context(direction=MarketDirection.BAIXA),
        operational_state=make_state(),
    )

    assert decision.decision == FinalDecision.AGUARDAR
    assert "incompatível" in decision.reason


def test_risk_limit_blocks_execution():
    decision = DecisionEngine(
        RiskManager(max_operations=3)
    ).evaluate(
        analysis=make_analysis(),
        market_context=make_context(),
        operational_state=make_state(trades_today=3),
    )

    assert decision.decision == FinalDecision.BLOQUEAR
    assert "Limite de operações" in decision.reason


def test_signal_quality_matches_actionable_analysis():
    quality = SignalQualityEvaluator().evaluate(make_analysis(score=100.0))

    assert quality.actionable is True
    assert quality.score == 100.0
    assert quality.level == SignalLevel.FORTE


def test_decision_snapshot_preserves_final_factors():
    analysis = make_analysis(score=100.0)
    quality = SignalQualityEvaluator().evaluate(analysis)
    state = make_state()
    context = make_context()
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=state,
    )

    snapshot = DecisionSnapshot.from_results(
        analysis=analysis,
        quality=quality,
        decision=decision,
        market_context=context,
        operational_state=state,
    )

    assert snapshot.signal == "COMPRA"
    assert snapshot.analysis_score == 100.0
    assert snapshot.quality_level == "FORTE"
    assert snapshot.decision == FinalDecision.EXECUTAR
    assert snapshot.market_direction == "ALTA"
    assert snapshot.operational_state_available is True
    assert snapshot.trades_today == 0
    assert "decisão=EXECUTAR" in snapshot.explain()


def test_demo_flow_executes_only_after_final_approval():
    logger = AuditLogger()
    flow = DemoFlow(
        decision_engine=DecisionEngine(RiskManager()),
        paper_executor=PaperExecutor(),
        audit_logger=logger,
    )

    result = flow.run(
        analysis=make_analysis(),
        market_context=make_context(),
        operational_state=make_state(),
        symbol="BTCUSD",
        amount=10.0,
        duration_seconds=60,
    )

    assert result.decision.decision == FinalDecision.EXECUTAR
    assert result.execution is not None
    assert result.execution.accepted is True
    assert result.quality.level == SignalLevel.FORTE
    assert [event.event_type for event in logger.events()] == [
        AuditEventType.ANALYSIS,
        AuditEventType.DECISION,
        AuditEventType.EXECUTION,
    ]


def test_demo_flow_does_not_execute_when_risk_blocks():
    logger = AuditLogger()
    flow = DemoFlow(
        decision_engine=DecisionEngine(RiskManager(max_operations=1)),
        paper_executor=PaperExecutor(),
        audit_logger=logger,
    )

    result = flow.run(
        analysis=make_analysis(),
        market_context=make_context(),
        operational_state=make_state(trades_today=1),
        symbol="BTCUSD",
        amount=10.0,
        duration_seconds=60,
    )

    assert result.decision.decision == FinalDecision.BLOQUEAR
    assert result.execution is None
    assert logger.events()[-1].event_type == AuditEventType.RISK
