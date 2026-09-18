from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmissionBoundary
from core.p114_real_safety_gate import RealSafetyGate
from execution.adapter_gateway import BrokerAdapterGateway, _RealDispatchCapability
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MutatingAdapter:
    supports_real_execution = True
    adapter_id = "adapter"

    def __init__(self):
        self.calls = 0

    def is_available(self):
        self.adapter_id = "changed-after-authorization"
        return True

    def execute(self, _request):
        self.calls += 1
        return ExecutionResult(True, "must never execute", "ext")


def _request(request_id):
    return ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL, request_id=request_id)


def _auth():
    return RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True, broker_id="fake"
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True
    )


def test_real_dispatch_revalidates_mutable_adapter_before_execute(tmp_path):
    adapter = MutatingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
    )

    result = gateway.execute(
        broker="fake", request_id="mutable-adapter", request=_request("mutable-adapter"),
        authorization=_auth(), admission=_admission(), safety=_safety(),
    )

    # The adapter was rejected before its irreversible execute() call.
    # UNKNOWN is intentional: the gateway cannot infer execution semantics
    # merely from the adapter-side failure, and the conservative state is
    # therefore preserved as non-replayable until reconciliation.
    assert result.status is RealGatewayStatus.UNKNOWN
    assert "adapter REAL mudou" in result.message
    assert adapter.calls == 0


def test_forged_real_capability_is_rejected():
    registry = BrokerRegistry()
    class Adapter:
        supports_real_execution = True
        adapter_id = "adapter"
        def is_available(self): return True
        def execute(self, _request): return ExecutionResult(True, "bad", "ext")
    adapter = Adapter()
    registry.register("fake", adapter)
    gateway = BrokerAdapterGateway(registry)
    forged = _RealDispatchCapability(adapter, "adapter", "fake", "r1", "auth")
    result = gateway._execute_real(
        "fake", _request("r1"), capability=forged, request_id="r1", authorization_id="auth"
    )
    assert result.accepted is False
    assert adapter.is_available() is True
