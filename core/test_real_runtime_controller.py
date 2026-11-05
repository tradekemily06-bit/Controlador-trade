from pathlib import Path

from core.real_runtime_controller import RealRuntimeController


class FakeKillSwitch:
    def allows_execution(self):
        return True


class FakeRecovery:
    def assess(self):
        from core.recovery_coordinator import RecoveryAssessment, RecoveryState
        return RecoveryAssessment(RecoveryState.FRESH, ())


class FakeRuntime:
    def __init__(self, tmp_path):
        from execution.execution_ledger import ExecutionLedger
        from execution.execution_lifecycle import ExecutionLifecycleStore
        self.execution_lifecycle = ExecutionLifecycleStore(Path(tmp_path) / "lifecycle.json")
        self.kill_switch = FakeKillSwitch()
        self.market_data = type("MarketData", (), {"report": type("Report", (), {"safe_for_analysis": True})()})()
        self.recovery = FakeRecovery()
        self.execution_ledger = ExecutionLedger(Path(tmp_path) / "ledger.json")


def test_real_controller_fails_closed_without_explicit_deployment_flags(monkeypatch, tmp_path):
    for name in (
        "CONTROLADOR_REAL_AUTHORIZATION_ID",
        "CONTROLADOR_REAL_AUDIT_ID",
        "CONTROLADOR_REAL_ADMISSION_ID",
        "CONTROLADOR_REAL_EXPLICITLY_ENABLED",
        "CONTROLADOR_REAL_EXECUTION_ALLOWED",
        "CONTROLADOR_REAL_AUDIT_VERIFIED",
        "CONTROLADOR_REAL_RISK_APPROVED",
    ):
        monkeypatch.delenv(name, raising=False)

    controller = RealRuntimeController(runtime=FakeRuntime(tmp_path), root=tmp_path)
    status = controller.status()
    assert status["authorization_active"] is False
    assert status["safety_ready"] is False
    assert status["admitted"] is False


def test_real_controller_prepare_requires_all_explicit_prerequisites(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROLADOR_REAL_AUTHORIZATION_ID", "auth")
    monkeypatch.setenv("CONTROLADOR_REAL_AUDIT_ID", "audit")
    monkeypatch.setenv("CONTROLADOR_REAL_ADMISSION_ID", "admission")
    monkeypatch.setenv("CONTROLADOR_REAL_EXPLICITLY_ENABLED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_EXECUTION_ALLOWED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_AUDIT_VERIFIED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_RISK_APPROVED", "true")

    controller = RealRuntimeController(runtime=FakeRuntime(tmp_path), root=tmp_path, symbol="EURUSD")
    status = controller.status()
    assert status["authorization_active"] is True
    assert status["safety_ready"] is False or status["admitted"] is False


def test_real_close_requires_accepted_ledger_state_before_adapter_access():
    source = (Path(__file__).parent / "real_runtime_controller.py").read_text(encoding="utf-8")
    method = source.split("    def close_and_reconcile(", 1)[1].split(
        "    def reconcile(", 1
    )[0]

    state_guard = "record.status is not ExecutionLedgerStatus.ACCEPTED"
    assert state_guard in method
    assert method.index(state_guard) < method.index("self.registry.get(self.broker_id)")


def test_real_close_rejects_blank_external_id_before_ledger_access():
    source = (Path(__file__).parent / "real_runtime_controller.py").read_text(encoding="utf-8")
    method = source.split("    def close_and_reconcile(", 1)[1].split(
        "    def reconcile(", 1
    )[0]

    validation = "not isinstance(external_id, str) or not external_id.strip()"
    assert validation in method
    assert method.index(validation) < method.index(
        "self.runtime.execution_ledger.record_for(request_id)"
    )


def test_real_reconcile_rejects_non_boolean_outcome_before_gateway_call():
    source = (Path(__file__).parent / "real_runtime_controller.py").read_text(encoding="utf-8")
    method = source.split("    def reconcile(", 1)[1]

    validation = "if not isinstance(executed, bool):"
    assert validation in method
    assert method.index(validation) < method.index("self.gateway.reconcile_unknown")
    assert "executed=executed" in method
    assert "executed=bool(executed)" not in method
