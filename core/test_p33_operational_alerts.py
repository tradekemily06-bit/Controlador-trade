from datetime import datetime, timezone

from core.p21_observability import HealthState, RuntimeHealth
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrityReport
from core.p33_operational_alerts import AlertSeverity, OperationalAlertMonitor
from core.recovery_coordinator import RecoveryState
from core.unified_safety_gate import SafetyGateReport, SafetyGateState


def runtime(state=HealthState.HEALTHY):
    return RuntimeHealth(state, 1, 0, 0, RecoveryState.FRESH, "runtime ok")


def market(health=MarketDataHealth.HEALTHY):
    return MarketDataIntegrityReport(health, 10, 60, 0, False, "market ok")


def safety(state=SafetyGateState.READY_DEMO, reasons=("ok",)):
    return SafetyGateReport(state, reasons)


def test_healthy_state_has_no_incident_alerts():
    report = OperationalAlertMonitor().assess(runtime(), market(), safety())
    assert report.alerts == ()
    assert not report.has_critical
    assert not report.has_warnings


def test_blocked_runtime_is_critical():
    report = OperationalAlertMonitor().assess(
        runtime(HealthState.BLOCKED), market(), safety()
    )
    assert [a.code for a in report.alerts] == ["RUNTIME_BLOCKED"]
    assert report.alerts[0].severity is AlertSeverity.CRITICAL


def test_market_degradation_is_warning_and_invalid_is_critical():
    warning = OperationalAlertMonitor().assess(
        runtime(), market(MarketDataHealth.STALE), safety()
    )
    assert warning.alerts[0].severity is AlertSeverity.WARNING

    critical = OperationalAlertMonitor().assess(
        runtime(), market(MarketDataHealth.INVALID), safety()
    )
    assert critical.alerts[0].severity is AlertSeverity.CRITICAL


def test_safety_not_ready_is_critical_and_preserves_reasons():
    report = OperationalAlertMonitor().assess(
        runtime(), market(), safety(SafetyGateState.NOT_READY, ("kill switch ativo", "recovery não seguro"))
    )
    assert report.alerts[-1].code == "SAFETY_NOT_READY"
    assert report.alerts[-1].severity is AlertSeverity.CRITICAL
    assert "kill switch ativo" in report.alerts[-1].message
    assert "recovery não seguro" in report.alerts[-1].message


def test_alert_order_is_deterministic():
    report = OperationalAlertMonitor().assess(
        runtime(HealthState.ATTENTION),
        market(MarketDataHealth.GAP),
        safety(SafetyGateState.NOT_READY, ("recovery pendente",)),
    )
    assert [a.code for a in report.alerts] == [
        "RUNTIME_ATTENTION",
        "MARKET_DATA_DEGRADED",
        "SAFETY_NOT_READY",
    ]


def test_invalid_inputs_fail_closed():
    monitor = OperationalAlertMonitor()
    now = datetime.now(timezone.utc)
    assert now is not None
    for args in ((object(), market(), safety()), (runtime(), object(), safety()), (runtime(), market(), object())):
        try:
            monitor.assess(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("entrada inválida deveria ser rejeitada")
