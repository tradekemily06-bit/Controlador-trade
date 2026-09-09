from core.kill_switch import KillSwitch
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.recovery_coordinator import RecoveryAssessment, RecoveryState
from core.runtime_config import RuntimeConfig
from core.unified_safety_gate import SafetyGateState, UnifiedSafetyGate
from execution.ports import ExecutionMode


def config():
    return RuntimeConfig("EURUSD", "1m", 10.0, 60)


def market(health=MarketDataHealth.HEALTHY, *, stale=False, gap_count=0):
    return MarketDataIntegrityReport(health, 1, 60, gap_count, stale, "ok")


def recovery(state=RecoveryState.FRESH):
    return RecoveryAssessment(state, None, (), (), "ok")


def test_ready_demo_when_all_safe():
    report = UnifiedSafetyGate(kill_switch=KillSwitch()).evaluate(config=config(), market_data=market(), recovery=recovery())
    assert report.state is SafetyGateState.READY_DEMO
    assert report.ready is True


def test_active_kill_switch_blocks():
    switch = KillSwitch()
    switch.activate("teste")
    report = UnifiedSafetyGate(kill_switch=switch).evaluate(config=config(), market_data=market(), recovery=recovery())
    assert report.state is SafetyGateState.NOT_READY


def test_unhealthy_data_blocks():
    report = UnifiedSafetyGate(kill_switch=KillSwitch()).evaluate(config=config(), market_data=market(MarketDataHealth.STALE), recovery=recovery())
    assert report.state is SafetyGateState.NOT_READY


def test_inconsistent_healthy_report_blocks():
    report = UnifiedSafetyGate(kill_switch=KillSwitch()).evaluate(config=config(), market_data=market(stale=True), recovery=recovery())
    assert report.state is SafetyGateState.NOT_READY


def test_recovery_reconciliation_blocks():
    report = UnifiedSafetyGate(kill_switch=KillSwitch()).evaluate(config=config(), market_data=market(), recovery=recovery(RecoveryState.REQUIRES_RECONCILIATION))
    assert report.state is SafetyGateState.NOT_READY


def test_real_config_cannot_be_created():
    try:
        RuntimeConfig("EURUSD", "1m", 10.0, 60, mode=ExecutionMode.REAL)
    except ValueError:
        return
    raise AssertionError("REAL deveria permanecer bloqueado")
