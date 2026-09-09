from datetime import datetime, timezone

from audit.events import AuditEventType, AuditLogger
from core.decision_engine import DecisionEngine, FinalDecision
from core.market_context import MarketContext, MarketContextResult, MarketDirection
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.risk_manager import RiskManager
from core.runtime_config import RuntimeConfig
from core.signal_quality import SignalLevel
from core.demo_readiness import DemoReadiness
from core.kill_switch import KillSwitch
from core.unified_safety_gate import UnifiedSafetyGate
from execution.demo_coordinator import DemoExecutionCoordinator
from execution.demo_flow import DemoFlow
from execution.gateway import ExecutionGateway
from execution.paper import PaperExecutor


def make_state() -> OperationalState:
    return OperationalState(balance=1000.0, realized_pnl=0.0, trades_today=0, consecutive_losses=0, market_open=True)


def make_context() -> MarketContextResult:
    return MarketContextResult(MarketContext.FAVORAVEL, 90.0, "Contexto favorável.", MarketDirection.ALTA)


def make_analysis(signal: Signal = Signal.COMPRA) -> AnalysisResult:
    return AnalysisResult(signal, 90.0, "Sinal confirmado.", True, "TEST", "5m")


def make_config() -> RuntimeConfig:
    return RuntimeConfig(symbol="TEST", timeframe="5m", amount=10.0, duration_seconds=60)


def make_market() -> MarketDataIntegrityReport:
    return MarketDataIntegrityReport(MarketDataHealth.HEALTHY, 1, None, 0, False, "healthy")


def make_recovery() -> RecoveryAssessment:
    return RecoveryAssessment(RecoveryState.FRESH, None, (), (), "fresh")


def make_flow() -> tuple[DemoFlow, AuditLogger, PaperExecutor]:
    logger = AuditLogger()
    executor = PaperExecutor()
    kill_switch = KillSwitch()
    gateway = ExecutionGateway(executor, kill_switch)
    readiness = DemoReadiness(UnifiedSafetyGate(kill_switch=kill_switch))
    coordinator = DemoExecutionCoordinator(readiness=readiness, gateway=gateway)
    return DemoFlow(decision_engine=DecisionEngine(RiskManager()), demo_coordinator=coordinator, audit_logger=logger, request_id_factory=lambda: "demo-flow-1", clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)), logger, executor


def run_flow(flow: DemoFlow, *, analysis: AnalysisResult | None = None, **overrides):
    values = {"analysis": analysis or make_analysis(), "market_context": make_context(), "operational_state": make_state(), "symbol": "TEST", "amount": 10.0, "duration_seconds": 60, "config": make_config(), "market_data": make_market(), "recovery": make_recovery()}
    values.update(overrides)
    return flow.run(**values)


def test_demo_flow_executes_through_coordinator():
    flow, logger, executor = make_flow()
    result = run_flow(flow)
    assert result.decision.decision == FinalDecision.EXECUTAR
    assert result.execution is not None and result.execution.accepted
    assert result.quality.actionable and result.quality.level == SignalLevel.FORTE
    assert len(executor.executions()) == 1
    assert result.execution_result is not None and result.execution_result.gateway is not None and result.execution_result.gateway.accepted
    assert [event.event_type for event in logger.events()] == [AuditEventType.ANALYSIS, AuditEventType.DECISION, AuditEventType.EXECUTION]
    assert logger.events()[0].data["quality_level"] == "FORTE"
    assert logger.events()[1].data["quality_score"] == 80.0


def test_demo_flow_does_not_execute_when_decision_is_aguardar():
    flow, logger, executor = make_flow()
    result = run_flow(flow, analysis=make_analysis(Signal.AGUARDAR))
    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.execution is None and result.execution_result is None
    assert result.quality.level == SignalLevel.NENHUMA and not result.quality.actionable
    assert executor.executions() == ()
    assert [event.event_type for event in logger.events()] == [AuditEventType.ANALYSIS, AuditEventType.DECISION, AuditEventType.RISK]


def test_demo_flow_does_not_execute_without_operational_state():
    flow, _, executor = make_flow()
    result = run_flow(flow, operational_state=None)
    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.execution is None and result.execution_result is None
    assert result.quality.level == SignalLevel.FORTE
    assert executor.executions() == ()


def test_demo_flow_does_not_execute_when_context_is_unfavorable():
    flow, _, executor = make_flow()
    context = MarketContextResult(MarketContext.DESFAVORAVEL, 20.0, "Contexto desfavorável.", MarketDirection.ALTA)
    result = run_flow(flow, market_context=context)
    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.execution is None and result.execution_result is None
    assert result.quality.level == SignalLevel.FORTE
    assert executor.executions() == ()


def test_demo_flow_blocks_before_executor_when_market_is_not_healthy():
    flow, _, executor = make_flow()
    stale = MarketDataIntegrityReport(MarketDataHealth.STALE, 1, None, 0, True, "stale")
    result = run_flow(flow, market_data=stale)
    assert result.decision.decision == FinalDecision.EXECUTAR
    assert result.execution is None
    assert result.execution_result is not None and not result.execution_result.readiness.ready
    assert executor.executions() == ()


def test_demo_flow_uses_demo_execution_mode():
    flow, _, executor = make_flow()
    result = run_flow(flow)
    assert result.execution_result is not None and result.execution_result.gateway is not None
    assert result.execution_result.gateway.execution is not None
    assert result.execution_result.gateway.execution.request_id == "demo-flow-1"
    assert result.execution_result.gateway.execution.mode.value == "DEMO"
    assert len(executor.executions()) == 1
