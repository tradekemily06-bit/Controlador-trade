from datetime import datetime, timezone

from core.demo_readiness import DemoReadiness
from core.execution_intent import ExecutionIntent
from core.kill_switch import KillSwitch
from core.models import Signal
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.runtime_config import RuntimeConfig
from core.unified_safety_gate import UnifiedSafetyGate
from execution.demo_coordinator import DemoExecutionCoordinator
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionResult


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "demo aceito", "demo-1")


def config():
    return RuntimeConfig(symbol="EURUSD", timeframe="5m", amount=10.0, duration_seconds=60)


def market():
    return MarketDataIntegrityReport(MarketDataHealth.HEALTHY, 1, None, 0, False, "healthy")


def recovery():
    return RecoveryAssessment(RecoveryState.FRESH, None, (), (), "fresh")


def intent():
    return ExecutionIntent("req-31", "EURUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO, datetime(2026, 1, 1, tzinfo=timezone.utc))


def coordinator():
    executor = FakeExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())
    readiness = DemoReadiness(UnifiedSafetyGate(kill_switch=KillSwitch()))
    return DemoExecutionCoordinator(readiness=readiness, gateway=gateway), executor


def test_ready_demo_reaches_gateway_once():
    coordinator, executor = coordinator()
    result = coordinator.execute(config=config(), market_data=market(), recovery=recovery(), intent=intent())
    assert result.readiness.ready
    assert result.gateway is not None
    assert result.gateway.status is GatewayStatus.ACCEPTED
    assert result.executed
    assert executor.calls == 1


def test_unready_market_never_calls_executor():
    coordinator, executor = coordinator()
    bad_market = MarketDataIntegrityReport(MarketDataHealth.STALE, 1, None, 0, True, "stale")
    result = coordinator.execute(config=config(), market_data=bad_market, recovery=recovery(), intent=intent())
    assert not result.readiness.ready
    assert result.gateway is None
    assert executor.calls == 0


def test_missing_intent_never_calls_executor():
    coordinator, executor = coordinator()
    result = coordinator.execute(config=config(), market_data=market(), recovery=recovery(), intent=None)
    assert not result.readiness.ready
    assert result.gateway is None
    assert executor.calls == 0
