from datetime import datetime, timezone

from core.demo_readiness import DemoReadiness
from core.execution_intent import ExecutionIntent
from core.models import Signal
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.runtime_config import RuntimeConfig
from core.unified_safety_gate import UnifiedSafetyGate
from core.kill_switch import KillSwitch
from execution.ports import ExecutionMode


def intent():
    return ExecutionIntent("req-30", "EURUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO, datetime(2026, 1, 1, tzinfo=timezone.utc))


def config():
    return RuntimeConfig(symbol="EURUSD", timeframe="5m", amount=10.0, duration_seconds=60)


def market():
    return MarketDataIntegrityReport(MarketDataHealth.HEALTHY, 1, None, 0, False, "healthy")


def recovery():
    return RecoveryAssessment(RecoveryState.FRESH, None, (), (), "fresh")


def test_ready_requires_all_safety_dependencies_and_intent():
    report = DemoReadiness(UnifiedSafetyGate(kill_switch=KillSwitch())).evaluate(
        config=config(), market_data=market(), recovery=recovery(), intent=intent()
    )
    assert report.ready


def test_missing_intent_blocks_readiness():
    report = DemoReadiness(UnifiedSafetyGate(kill_switch=KillSwitch())).evaluate(
        config=config(), market_data=market(), recovery=recovery(), intent=None
    )
    assert not report.ready
    assert "intenção de execução ausente" in report.reasons


def test_kill_switch_blocks_readiness():
    switch = KillSwitch()
    switch.activate("P30")
    report = DemoReadiness(UnifiedSafetyGate(kill_switch=switch)).evaluate(
        config=config(), market_data=market(), recovery=recovery(), intent=intent()
    )
    assert not report.ready
