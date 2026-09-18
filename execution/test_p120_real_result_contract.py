from core.kill_switch import KillSwitch
from pathlib import Path

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MissingExternalIdAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but no durable reference", None)


def test_accepted_without_external_id_is_unknown_and_persisted(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", MissingExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="missing-external-id", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("missing-external-id") is ExecutionLedgerStatus.UNKNOWN


class FailingAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        raise RuntimeError("timeout after send")


def test_adapter_transport_failure_is_unknown_not_rejected(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", FailingAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="transport-uncertain", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("transport-uncertain") is ExecutionLedgerStatus.UNKNOWN


class RejectedWithExternalIdAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(False, "rejected with broker reference", "EXT-REJECTED-1")


def test_rejected_response_with_external_id_is_unknown_and_reconcilable(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", RejectedWithExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    result = gateway.execute(
        broker="fake", request_id="rejected-with-id", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("rejected-with-id") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.external_id("rejected-with-id") == "EXT-REJECTED-1"


class ActivatingAdapter:
    def __init__(self, kill_switch):
        self.kill_switch = kill_switch
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        self.kill_switch.activate("test activation at broker boundary")
        return ExecutionResult(True, "accepted", f"EXT-{self.calls}")


def test_live_kill_switch_overrides_stale_ready_report_at_real_boundary(tmp_path: Path):
    kill_switch = KillSwitch()
    adapter = ActivatingAdapter(kill_switch)
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=kill_switch)
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    first = gateway.execute(
        broker="fake", request_id="live-switch-1", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )
    assert first.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1
    assert kill_switch.state.enabled is True

    second = gateway.execute(
        broker="fake", request_id="live-switch-2", request=request,
        authorization=authorization, admission=admission, safety=safety,
    )
    assert second.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1
    assert ledger.status("live-switch-2") is ExecutionLedgerStatus.UNKNOWN
