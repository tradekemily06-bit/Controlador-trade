from pathlib import Path

from core.real_runtime_controller import RealRuntimeController
from core.real_user_authorization import RealUserAuthorizationStore


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


def test_real_controller_fails_closed_without_explicit_ecosystem_authorization(monkeypatch, tmp_path):
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
    for name in (
        "CONTROLADOR_REAL_AUTHORIZATION_ID",
        "CONTROLADOR_REAL_AUDIT_ID",
        "CONTROLADOR_REAL_ADMISSION_ID",
        "CONTROLADOR_REAL_EXPLICITLY_ENABLED",
        "CONTROLADOR_REAL_EXECUTION_ALLOWED",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("CONTROLADOR_REAL_AUDIT_VERIFIED", "true")
    monkeypatch.setenv("CONTROLADOR_REAL_RISK_APPROVED", "true")

    store = RealUserAuthorizationStore(Path(tmp_path) / "ecosystem-state.sqlite")
    authorization = store.enable()

    controller = RealRuntimeController(runtime=FakeRuntime(tmp_path), root=tmp_path, symbol="EURUSD")
    status = controller.status()
    assert status["authorization_active"] is True
    assert status["user_authorization_enabled"] is True
    assert status["authorization_source"] == "ecosystem"
    assert status["audit_verified"] is True
    assert status["risk_approved"] is True
    assert status["safety_ready"] is False or status["admitted"] is False
    assert status["real_execution_allowed"] is True
    assert status["explicitly_enabled"] is True
    assert authorization.authorization_id != "real-disabled"
