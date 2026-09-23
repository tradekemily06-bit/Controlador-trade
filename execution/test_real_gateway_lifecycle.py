from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class FakeAdapter:
    def __init__(self, result=None):
        self.result = result or ExecutionResult(True, "ok", "EXT-1")
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return self.result


def _request():
    return ExecutionRequest("EURUSD", Signal.COMPRA, 0.01, 60, ExecutionMode.REAL, "r-1")


def _guards():
    authorization = RealExecutionAuthorization("a-1", "audit-1", "ic", "mt5", True, True)
    safety = RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )
    admission = RealAdmissionBoundary().admit(
        admission_id="adm-1",
        audit_id="audit-1",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="ic",
    )
    return authorization, admission, safety


def test_real_gateway_projects_ledger_and_lifecycle(tmp_path):
    adapter = FakeAdapter()
    registry = BrokerRegistry()
    registry.register("ic", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)
    authorization, admission, safety = _guards()

    result = gateway.execute(
        broker="ic",
        request_id="r-1",
        request=_request(),
        authorization=authorization,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert ledger.status("r-1") is ExecutionLedgerStatus.ACCEPTED
    assert lifecycle.get("r-1").state is ExecutionLifecycleState.ACCEPTED
    assert adapter.calls == 1


def test_real_gateway_unknown_projects_unknown_lifecycle(tmp_path):
    adapter = FakeAdapter(ExecutionResult(True, "accepted without durable id", None))
    registry = BrokerRegistry()
    registry.register("ic", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle)
    authorization, admission, safety = _guards()

    result = gateway.execute(
        broker="ic",
        request_id="r-1",
        request=_request(),
        authorization=authorization,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("r-1") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("r-1").state is ExecutionLifecycleState.UNKNOWN
