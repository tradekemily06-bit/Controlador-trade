from datetime import datetime, timezone

from audit.events import AuditEventType, AuditLogger
from core.decision_engine import DecisionEngine, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.demo_readiness import DemoReadiness
from core.kill_switch import KillSwitch
from core.market_context import MarketContext, MarketContextResult
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.risk_manager import RiskManager
from core.runtime_config import RuntimeConfig
from core.signal_quality import SignalLevel, SignalQualityEvaluator
from core.unified_safety_gate import UnifiedSafetyGate
from execution.demo_coordinator import DemoExecutionCoordinator
from execution.demo_flow import DemoFlow
from execution.gateway import ExecutionGateway
from execution.paper import PaperExecutor


def make_analysis(signal=Signal.COMPRA, score=100.0, confirmed=True):
    return AnalysisResult(signal=signal, score=score, reason="Teste de auditoria P1.10.", confirmed=confirmed, symbol="BTCUSD", timeframe="5m")


def make_state(*, trades_today=0, consecutive_losses=0, realized_pnl=0.0):
    return OperationalState(realized_pnl=realized_pnl, trades_today=trades_today, consecutive_losses=consecutive_losses)


def make_context(direction=MarketDirection.ALTA, score=100.0):
    return MarketContextResult(context=MarketContext.FAVORAVEL, score=score, reason="Contexto favorável para teste.", direction=direction)


def make_config():
    return RuntimeConfig(symbol="BTCUSD", timeframe="5m", amount=10.0, duration_seconds=60)


def make_market():
    return MarketDataIntegrityReport(MarketDataHealth.HEALTHY, 1, None, 0, False, "healthy")


def make_recovery():
    return RecoveryAssessment(RecoveryState.FRESH, None, (), (), "fresh")


def make_demo_flow(risk_manager=None):
    logger = AuditLogger()
    executor = PaperExecutor()
    kill_switch = KillSwitch()
    gateway = ExecutionGateway(executor, kill_switch)
    readiness = DemoReadiness(UnifiedSafetyGate(kill_switch=kill_switch))
    coordinator = DemoExecutionCoordinator(readiness=readiness, gateway=gateway)
    flow = DemoFlow(
        decision_engine=DecisionEngine(risk_manager or RiskManager()),
        demo_coordinator=coordinator,
        audit_logger=logger,
        request_id_factory=lambda: "p1-10-demo",
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return flow, logger, executor


def test_full_executable_path_reaches_execute():
    decision = DecisionEngine(RiskManager()).evaluate(analysis=make_analysis(), market_context=make_context(), operational_state=make_state())
    assert decision.decision == FinalDecision.EXECUTAR
    assert decision.signal == Signal.COMPRA


def test_missing_operational_state_never_executes():
    decision = DecisionEngine(RiskManager()).evaluate(analysis=make_analysis(), market_context=make_context(), operational_state=None)
    assert decision.decision == FinalDecision.AGUARDAR
    assert "Estado operacional" in decision.reason


def test_missing_market_context_never_executes():
    decision = DecisionEngine(RiskManager()).evaluate(analysis=make_analysis(), market_context=None, operational_state=make_state())
    assert decision.decision == FinalDecision.AGUARDAR
    assert "Contexto de mercado" in decision.reason


def test_incompatible_direction_never_executes():
    decision = DecisionEngine(RiskManager()).evaluate(analysis=make_analysis(signal=Signal.COMPRA), market_context=make_context(direction=MarketDirection.BAIXA), operational_state=make_state())
    assert decision.decision == FinalDecision.AGUARDAR
    assert "incompatível" in decision.reason


def test_risk_limit_blocks_execution():
    decision = DecisionEngine(RiskManager(max_operations=3)).evaluate(analysis=make_analysis(), market_context=make_context(), operational_state=make_state(trades_today=3))
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
    decision = DecisionEngine(RiskManager()).evaluate(analysis=analysis, market_context=context, operational_state=state)
    snapshot = DecisionSnapshot.from_results(analysis=analysis, quality=quality, decision=decision, market_context=context, operational_state=state)
    assert snapshot.signal == "COMPRA"
    assert snapshot.analysis_score == 100.0
    assert snapshot.quality_level == "FORTE"
    assert snapshot.decision == FinalDecision.EXECUTAR
    assert snapshot.market_direction == "ALTA"
    assert snapshot.operational_state_available is True
    assert snapshot.trades_today == 0
    assert "decisão=EXECUTAR" in snapshot.explain()


def test_demo_flow_executes_only_after_final_approval():
    flow, logger, executor = make_demo_flow()
    result = flow.run(analysis=make_analysis(), market_context=make_context(), operational_state=make_state(), symbol="BTCUSD", amount=10.0, duration_seconds=60, config=make_config(), market_data=make_market(), recovery=make_recovery())
    assert result.decision.decision == FinalDecision.EXECUTAR
    assert result.execution is not None and result.execution.accepted
    assert result.quality.level == SignalLevel.FORTE
    assert [event.event_type for event in logger.events()] == [AuditEventType.ANALYSIS, AuditEventType.DECISION, AuditEventType.EXECUTION]
    assert len(executor.executions()) == 1


def test_demo_flow_does_not_execute_when_risk_blocks():
    flow, logger, executor = make_demo_flow(RiskManager(max_operations=1))
    result = flow.run(analysis=make_analysis(), market_context=make_context(), operational_state=make_state(trades_today=1), symbol="BTCUSD", amount=10.0, duration_seconds=60, config=make_config(), market_data=make_market(), recovery=make_recovery())
    assert result.decision.decision == FinalDecision.BLOQUEAR
    assert result.execution is None
    assert executor.executions() == ()
    assert logger.events()[-1].event_type == AuditEventType.RISK
