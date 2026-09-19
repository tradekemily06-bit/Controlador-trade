import threading
from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from core.operation_memory import OperationMemory
from core.operational_safety_store import OperationalSafetyStore
from core.recovery_coordinator import RecoveryCoordinator
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def _contracts():
    authorization = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm",
        audit_id="audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )
    return authorization, admission, safety


def _gateway(tmp_path: Path, adapter, *, safety_store=None):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    return (
        RealExecutionGateway(
            BrokerAdapterGateway(registry),
            ledger,
            lifecycle=lifecycle,
            recovery=recovery,
            kill_switch=KillSwitch(),
            safety_store=safety_store or OperationalSafetyStore(tmp_path / "operational-safety.json"),
        ),
        ledger,
        lifecycle,
    )


def test_p5_crash_window_after_external_dispatch_never_replays(tmp_path: Path):
    class HardInterruptAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            raise KeyboardInterrupt("process interrupted after dispatch boundary")

    adapter = HardInterruptAdapter()
    gateway, ledger, lifecycle = _gateway(tmp_path, adapter)
    authorization, admission, safety = _contracts()

    try:
        gateway.execute(
            broker="fake",
            request_id="crash-window",
            request=_request(),
            authorization=authorization,
            admission=admission,
            safety=safety,
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("hard interruption must propagate")

    assert adapter.calls == 1
    assert ledger.status("crash-window") is ExecutionLedgerStatus.RESERVED
    assert lifecycle.get("crash-window").state is ExecutionLifecycleState.PENDING

    restarted, restarted_ledger, restarted_lifecycle = _gateway(tmp_path, adapter)
    retry = restarted.execute(
        broker="fake",
        request_id="crash-window",
        request=_request(),
        authorization=authorization,
        admission=admission,
        safety=safety,
    )

    assert retry.status is RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    assert restarted_ledger.status("crash-window") is ExecutionLedgerStatus.RESERVED
    assert restarted_lifecycle.get("crash-window").state is ExecutionLifecycleState.PENDING


def test_p5_high_contention_same_request_id_has_at_most_one_dispatch(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.lock = threading.Lock()
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            with self.lock:
                self.calls += 1
                call_number = self.calls
            return ExecutionResult(True, f"accepted-{call_number}", f"EXT-CONTENTION-{call_number}")

    adapter = CountingAdapter()
    authorization, admission, safety = _contracts()
    gateways = [_gateway(tmp_path, adapter)[0] for _ in range(16)]
    results = []
    errors = []
    result_lock = threading.Lock()

    def run(gateway):
        try:
            result = gateway.execute(
                broker="fake",
                request_id="high-contention",
                request=_request(),
                authorization=authorization,
                admission=admission,
                safety=safety,
            )
            with result_lock:
                results.append(result)
        except Exception as exc:
            with result_lock:
                errors.append(exc)

    threads = [threading.Thread(target=run, args=(gateway,)) for gateway in gateways]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert adapter.calls == 1
    assert len(results) == 16
    assert sum(result.status is RealGatewayStatus.ADMITTED for result in results) == 1
    assert all(
        result.status in {RealGatewayStatus.ADMITTED, RealGatewayStatus.BLOCKED, RealGatewayStatus.UNKNOWN}
        for result in results
    )


def test_p5_persistent_kill_switch_blocks_final_dispatch(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "must-not-dispatch", "EXT-KILL")

    adapter = CountingAdapter()
    safety_store = OperationalSafetyStore(tmp_path / "safety.json")
    kill_switch = KillSwitch()
    kill_switch.activate("emergency test")
    safety_store.save_kill_switch(kill_switch)

    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle=lifecycle,
        recovery=recovery,
        kill_switch=KillSwitch(),
        safety_store=safety_store,
    )
    authorization, admission, safety = _contracts()

    result = gateway.execute(
        broker="fake",
        request_id="persistent-kill",
        request=_request(),
        authorization=authorization,
        admission=admission,
        safety=safety,
    )

    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ledger.status("persistent-kill") is ExecutionLedgerStatus.REJECTED
    assert lifecycle.get("persistent-kill").state is ExecutionLifecycleState.REJECTED
