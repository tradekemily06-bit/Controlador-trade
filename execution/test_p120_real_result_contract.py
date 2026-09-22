from pathlib import Path

from core.models import Signal
from core.kill_switch import KillSwitch
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MissingExternalIdAdapter:
    adapter_id = "adapter"
    supports_real_execution = True
    def is_available(self):
        return True

    def query_order_by_request_id(self, request_id):
        return None

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


class AcceptedAdapter:
    adapter_id = "adapter"
    supports_real_execution = True
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def query_order_by_request_id(self, request_id):
        return None

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted", "external-1")


class RejectedAdapter:
    adapter_id = "adapter"
    supports_real_execution = True
    def is_available(self):
        return True

    def query_order_by_request_id(self, request_id):
        return None

    def execute(self, request):
        return ExecutionResult(False, "rejected", None)


class RaisingAdapter:
    adapter_id = "adapter"
    supports_real_execution = True
    def is_available(self):
        return True

    def query_order_by_request_id(self, request_id):
        return None

    def execute(self, request):
        raise TimeoutError("timeout")


def _auth_and_safety():
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
    return authorization, admission, safety


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def test_real_gateway_projects_accepted_lifecycle(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", AcceptedAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, KillSwitch())
    authorization, admission, safety = _auth_and_safety()

    result = gateway.execute(
        broker="fake", request_id="accepted-1", request=_request(),
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert lifecycle.get("accepted-1").state is ExecutionLifecycleState.ACCEPTED


def test_real_gateway_projects_rejected_lifecycle(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", RejectedAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, KillSwitch())
    authorization, admission, safety = _auth_and_safety()

    result = gateway.execute(
        broker="fake", request_id="rejected-1", request=_request(),
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.REJECTED
    assert lifecycle.get("rejected-1").state is ExecutionLifecycleState.REJECTED


def test_real_gateway_projects_unknown_lifecycle(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", RaisingAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, KillSwitch())
    authorization, admission, safety = _auth_and_safety()

    result = gateway.execute(
        broker="fake", request_id="unknown-1", request=_request(),
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert lifecycle.get("unknown-1").state is ExecutionLifecycleState.UNKNOWN


def test_real_gateway_persists_accepted_external_id(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", AcceptedAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    authorization, admission, safety = _auth_and_safety()

    result = gateway.execute(
        broker="fake", request_id="accepted-ext", request=_request(),
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert ExecutionLedger(tmp_path / "ledger.json").external_id("accepted-ext") == "external-1"


def test_real_gateway_kill_switch_is_rechecked_at_dispatch(tmp_path: Path):
    class TripKillSwitch(KillSwitch):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def allows_execution(self):
            self.calls += 1
            return self.calls < 2

    registry = BrokerRegistry()
    adapter = AcceptedAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        kill_switch=TripKillSwitch(),
    )
    authorization, admission, safety = _auth_and_safety()

    result = gateway.execute(
        broker="fake", request_id="blocked-by-kill-switch", request=_request(),
        authorization=authorization, admission=admission, safety=safety,
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert ledger.status("blocked-by-kill-switch") is ExecutionLedgerStatus.RESERVED
    assert adapter.calls == 0
