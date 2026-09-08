from audit.events import AuditEventType, AuditLogger
from core.decision_engine import DecisionEngine, FinalDecision
from core.market_context import (
    MarketContext,
    MarketContextResult,
    MarketDirection,
)
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.risk_manager import RiskManager
from execution.demo_flow import DemoFlow
from execution.paper import PaperExecutor


def make_state() -> OperationalState:
    return OperationalState(
        balance=1000.0,
        realized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
        market_open=True,
    )


def make_context() -> MarketContextResult:
    return MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=90.0,
        direction=MarketDirection.ALTA,
        reason="Contexto favorável.",
    )


def make_analysis(signal: Signal = Signal.COMPRA) -> AnalysisResult:
    return AnalysisResult(
        signal=signal,
        score=90.0,
        reason="Sinal confirmado.",
        confirmed=True,
        symbol="TEST",
        timeframe="5m",
    )


def make_flow() -> tuple[DemoFlow, AuditLogger, PaperExecutor]:
    logger = AuditLogger()
    executor = PaperExecutor()
    engine = DecisionEngine(RiskManager())

    return (
        DemoFlow(
            decision_engine=engine,
            paper_executor=executor,
            audit_logger=logger,
        ),
        logger,
        executor,
    )


def test_demo_flow_executes_when_decision_is_approved():
    flow, logger, executor = make_flow()

    result = flow.run(
        analysis=make_analysis(),
        market_context=make_context(),
        operational_state=make_state(),
        symbol="TEST",
        amount=10.0,
        duration_seconds=60,
    )

    assert result.decision.decision == FinalDecision.EXECUTAR
    assert result.execution is not None
    assert result.execution.accepted is True
    assert len(executor.executions()) == 1

    event_types = [event.event_type for event in logger.events()]

    assert event_types == [
        AuditEventType.ANALYSIS,
        AuditEventType.DECISION,
        AuditEventType.EXECUTION,
    ]


def test_demo_flow_does_not_execute_when_decision_is_aguardar():
    flow, logger, executor = make_flow()

    result = flow.run(
        analysis=make_analysis(Signal.AGUARDAR),
        market_context=make_context(),
        operational_state=make_state(),
        symbol="TEST",
        amount=10.0,
        duration_seconds=60,
    )

    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.execution is None
    assert executor.executions() == ()

    event_types = [event.event_type for event in logger.events()]

    assert event_types == [
        AuditEventType.ANALYSIS,
        AuditEventType.DECISION,
        AuditEventType.RISK,
    ]


def test_demo_flow_does_not_execute_without_operational_state():
    flow, logger, executor = make_flow()

    result = flow.run(
        analysis=make_analysis(),
        market_context=make_context(),
        operational_state=None,
        symbol="TEST",
        amount=10.0,
        duration_seconds=60,
    )

    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.execution is None
    assert executor.executions() == ()


def test_demo_flow_does_not_execute_when_context_is_unfavorable():
    flow, logger, executor = make_flow()

    context = MarketContextResult(
        context=MarketContext.DESFAVORAVEL,
        score=20.0,
        direction=MarketDirection.ALTA,
        reason="Contexto desfavorável.",
    )

    result = flow.run(
        analysis=make_analysis(),
        market_context=context,
        operational_state=make_state(),
        symbol="TEST",
        amount=10.0,
        duration_seconds=60,
    )

    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.execution is None
    assert executor.executions() == ()
