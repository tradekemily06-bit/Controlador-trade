import threading
from threading import Lock, Thread
from pathlib import Path
from datetime import datetime, timezone
import pytest

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.p3_execution_reconciliation import ExecutionReconciliationCoordinator
from core.p3_external_reconciliation_service import ExternalExecutionReconciliationService
from core.operation_memory import OperationMemory
from core.operational_safety_store import OperationalSafetyStore
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def _contracts():
    auth = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
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
    return auth, admission, safety


def _real_gateway(adapter_gateway, ledger, lifecycle=None, recovery=None, *, kill_switch=None):
    lifecycle = lifecycle or ExecutionLifecycleStore(ledger.path.parent / "lifecycle.json")
    recovery = recovery or RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(ledger.path.parent / "runtime-checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    from core.kill_switch import KillSwitch
    return RealExecutionGateway(
        adapter_gateway,
        ledger,
        lifecycle=lifecycle,
        recovery=recovery,
        kill_switch=kill_switch or KillSwitch(),
        safety_store=OperationalSafetyStore(ledger.path.parent / "operational-safety.json"),
    )



def test_global_real_execution_lock_serializes_reconciliation_worker(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("global-race")
    ledger.bind_external_id("global-race", "EXT-GLOBAL")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "global-race",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "awaiting broker result",
        )
    )
    coordinator = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle)
    observation = ExternalOrderObservation(
        "EXT-GLOBAL",
        ExternalOrderStatus.EXECUTED,
        "broker confirms execution",
    )
    completed = threading.Event()
    errors = []

    def reconcile():
        try:
            coordinator.reconcile("global-race", "EXT-GLOBAL", observation)
        except Exception as exc:
            errors.append(exc)
        finally:
            completed.set()

    with ledger.real_execution_lock():
        worker = Thread(target=reconcile)
        worker.start()
        assert not completed.wait(0.15)
        assert ledger.status("global-race") is ExecutionLedgerStatus.RESERVED

    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not errors
    assert ledger.status("global-race") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("global-race").state is ExecutionLifecycleState.ACCEPTED


def test_two_real_gateway_instances_cannot_double_dispatch(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.lock = Lock()
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            with self.lock:
                self.calls += 1
            return ExecutionResult(True, "accepted", f"EXT-{self.calls}")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    path = tmp_path / "ledger.json"
    auth, admission, safety = _contracts()
    gateways = [
        _real_gateway(BrokerAdapterGateway(registry), ExecutionLedger(path)),
        _real_gateway(BrokerAdapterGateway(registry), ExecutionLedger(path)),
    ]
    results = []

    def run(gateway):
        results.append(
            gateway.execute(
                broker="fake",
                request_id="same-real-id",
                request=_request(),
                authorization=auth,
                admission=admission,
                safety=safety,
            )
        )

    threads = [Thread(target=run, args=(gateway,)) for gateway in gateways]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert adapter.calls == 1
    statuses = {result.status for result in results}
    assert RealGatewayStatus.ADMITTED in statuses
    assert statuses - {RealGatewayStatus.ADMITTED} <= {
        RealGatewayStatus.UNKNOWN,
        RealGatewayStatus.BLOCKED,
    }


def test_real_persistence_failure_after_dispatch_never_releases_request_for_retry(tmp_path: Path, monkeypatch):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-FAIL")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    path = tmp_path / "ledger.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(path)
    gateway = _real_gateway(BrokerAdapterGateway(registry), ledger)

    original = ledger.mark_accepted

    def fail_terminal(_request_id):
        raise OSError("terminal persistence failed")

    monkeypatch.setattr(ledger, "mark_accepted", fail_terminal)
    first = gateway.execute(
        broker="fake",
        request_id="persist-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1

    restarted = _real_gateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
    retry = restarted.execute(
        broker="fake",
        request_id="persist-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert retry.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    # The durable ledger remains RESERVED because the terminal write itself failed.
    assert ExecutionLedger(path).status("persist-failure").value == "RESERVED"
    assert original is not None

def test_real_rejection_persistence_failure_keeps_request_non_replayable(tmp_path: Path, monkeypatch):
    class RejectingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(False, "broker rejected")

    adapter = RejectingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    path = tmp_path / "ledger.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(path)
    gateway = _real_gateway(BrokerAdapterGateway(registry), ledger)

    def fail_terminal(_request_id):
        raise OSError("rejection persistence failed")

    monkeypatch.setattr(ledger, "mark_rejected", fail_terminal)
    first = gateway.execute(
        broker="fake",
        request_id="reject-persist-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1

    restarted = _real_gateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
    retry = restarted.execute(
        broker="fake",
        request_id="reject-persist-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert retry.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    assert ExecutionLedger(path).status("reject-persist-failure").value == "RESERVED"


def test_real_executor_exception_persists_unknown_and_restart_blocks_adapter(tmp_path: Path):
    class FailingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            raise RuntimeError("network uncertainty")

    adapter = FailingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    path = tmp_path / "ledger.json"
    auth, admission, safety = _contracts()
    gateway = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(path),
    )

    first = gateway.execute(
        broker="fake",
        request_id="executor-error",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.UNKNOWN
    assert ExecutionLedger(path).status("executor-error").value == "UNKNOWN"

    restarted = _real_gateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
    retry = restarted.execute(
        broker="fake",
        request_id="executor-error",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert retry.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1


def test_real_gateway_persists_lifecycle_terminal_state(tmp_path: Path):
    class AcceptedAdapter:
        def is_available(self):
            return True

        def execute(self, _request):
            return ExecutionResult(True, "accepted", "EXT-LIFE")

    registry = BrokerRegistry()
    registry.register("fake", AcceptedAdapter())
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    ).execute(
        broker="fake",
        request_id="real-lifecycle",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert ExecutionLifecycleStore(lifecycle_path).get("real-lifecycle").state is ExecutionLifecycleState.ACCEPTED


def test_real_gateway_broker_uncertainty_persists_unknown_in_both_authorities(tmp_path: Path):
    class UncertainAdapter:
        def is_available(self):
            return True

        def execute(self, _request):
            raise TimeoutError("broker timeout")

    registry = BrokerRegistry()
    registry.register("fake", UncertainAdapter())
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    ).execute(
        broker="fake",
        request_id="real-unknown-lifecycle",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ExecutionLedger(ledger_path).status("real-unknown-lifecycle").value == "UNKNOWN"
    assert ExecutionLifecycleStore(lifecycle_path).get("real-unknown-lifecycle").state is ExecutionLifecycleState.UNKNOWN


def test_real_gateway_rejected_persists_lifecycle_rejected(tmp_path: Path):
    class RejectingAdapter:
        def is_available(self):
            return True

        def execute(self, _request):
            return ExecutionResult(False, "rejected")

    registry = BrokerRegistry()
    registry.register("fake", RejectingAdapter())
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    ).execute(
        broker="fake",
        request_id="real-rejected-lifecycle",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.REJECTED
    assert ExecutionLifecycleStore(lifecycle_path).get("real-rejected-lifecycle").state is ExecutionLifecycleState.REJECTED


def test_real_accepted_without_external_id_marks_both_authorities_unknown(tmp_path: Path):
    class AcceptedWithoutIdentity:
        def is_available(self):
            return True

        def execute(self, _request):
            return ExecutionResult(True, "accepted but no broker identity", None)

    registry = BrokerRegistry()
    registry.register("fake", AcceptedWithoutIdentity())
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    ).execute(
        broker="fake",
        request_id="accepted-no-external-id",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ExecutionLedger(ledger_path).status("accepted-no-external-id").value == "UNKNOWN"
    assert ExecutionLifecycleStore(lifecycle_path).get("accepted-no-external-id").state is ExecutionLifecycleState.UNKNOWN


def test_real_accepted_terminal_persistence_failure_marks_lifecycle_unknown(tmp_path: Path, monkeypatch):
    class AcceptedAdapter:
        def is_available(self):
            return True

        def execute(self, _request):
            return ExecutionResult(True, "accepted", "EXT-POST-ACCEPT")

    registry = BrokerRegistry()
    registry.register("fake", AcceptedAdapter())
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)

    def fail_terminal(_request_id):
        raise OSError("terminal persistence failed")

    monkeypatch.setattr(ledger, "mark_accepted", fail_terminal)

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
    ).execute(
        broker="fake",
        request_id="accepted-terminal-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    durable_ledger = ExecutionLedger(ledger_path)
    assert durable_ledger.status("accepted-terminal-failure").value == "RESERVED"
    assert durable_ledger.external_id("accepted-terminal-failure") == "EXT-POST-ACCEPT"
    assert ExecutionLifecycleStore(lifecycle_path).get("accepted-terminal-failure").state is ExecutionLifecycleState.UNKNOWN


def test_reconcile_unknown_with_lifecycle_cannot_bypass_cross_store_authority(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("reconcile-cross-store")
    ledger.mark_unknown("reconcile-cross-store")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "reconcile-cross-store",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    gateway = _real_gateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
    )

    with pytest.raises(ValueError, match="external_id durável"):
        gateway.reconcile_unknown("reconcile-cross-store", observation=ExternalOrderObservation("", ExternalOrderStatus.EXECUTED, "missing identity"))

    assert ExecutionLedger(ledger_path).status("reconcile-cross-store").value == "UNKNOWN"
    assert ExecutionLifecycleStore(lifecycle_path).get("reconcile-cross-store").state is ExecutionLifecycleState.UNKNOWN



def test_real_lifecycle_pending_before_ledger_reserve_failure_blocks_restart_without_dispatch(tmp_path, monkeypatch):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-SHOULD-NOT-HAPPEN")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)

    def fail_reserve(_request_id):
        raise OSError("reserve persistence failed")

    monkeypatch.setattr(ledger, "reserve", fail_reserve)
    first = _real_gateway(BrokerAdapterGateway(registry), ledger, lifecycle).execute(
        broker="fake",
        request_id="pending-before-reserve",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ExecutionLedger(ledger_path).status("pending-before-reserve") is None
    # Reserve failed before lifecycle publication, so no phantom PENDING state is created.
    assert ExecutionLifecycleStore(lifecycle_path).get("pending-before-reserve") is None

    from core.operation_memory import OperationMemory
    from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
    from core.runtime_checkpoint import RuntimeCheckpointStore

    assessment = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    ).assess()
    assert assessment.state is RecoveryState.FRESH

    restarted = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    )
    retry = restarted.execute(
        broker="fake",
        request_id="pending-before-reserve",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert retry.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1


def test_two_real_gateways_with_lifecycle_still_dispatch_once(tmp_path):
    class CountingAdapter:
        def __init__(self):
            self.lock = Lock()
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            with self.lock:
                self.calls += 1
                call = self.calls
            return ExecutionResult(True, "accepted", f"EXT-LIFE-{call}")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()
    gateways = [
        _real_gateway(
            BrokerAdapterGateway(registry),
            ExecutionLedger(ledger_path),
            ExecutionLifecycleStore(lifecycle_path),
        )
        for _ in range(2)
    ]
    results = []

    def run(gateway):
        results.append(gateway.execute(
            broker="fake", request_id="same-real-lifecycle-id", request=_request(),
            authorization=auth, admission=admission, safety=safety,
        ))

    threads = [Thread(target=run, args=(gateway,)) for gateway in gateways]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert adapter.calls == 1
    assert len(results) == 2
    assert any(result.status == RealGatewayStatus.ADMITTED for result in results)
    assert ExecutionLedger(ledger_path).status("same-real-lifecycle-id").value == "ACCEPTED"
    assert ExecutionLifecycleStore(lifecycle_path).get("same-real-lifecycle-id").state is ExecutionLifecycleState.ACCEPTED


def test_real_gateway_binds_durable_request_id_into_broker_request(tmp_path):
    class CapturingAdapter:
        def __init__(self):
            self.received = None

        def is_available(self):
            return True

        def execute(self, request):
            self.received = request
            return ExecutionResult(True, "accepted", "EXT-ID")

    adapter = CapturingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    auth, admission, safety = _contracts()
    gateway = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
    )

    result = gateway.execute(
        broker="fake",
        request_id="durable-request-id",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.received.request_id == "durable-request-id"


def test_real_gateway_rejects_conflicting_payload_request_id(tmp_path):
    registry = BrokerRegistry()
    registry.register("fake", type("Adapter", (), {
        "is_available": lambda self: True,
        "execute": lambda self, request: ExecutionResult(True, "accepted", "EXT-CONFLICT"),
    })())
    auth, admission, safety = _contracts()
    gateway = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
    )

    conflicting = ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
        request_id="other-id",
    )
    result = gateway.execute(
        broker="fake",
        request_id="durable-id",
        request=conflicting,
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.REJECTED
    assert "difere" in result.message


def test_real_process_interrupt_after_broker_acceptance_never_replays(tmp_path):
    """A hard process interruption after broker side effect must fail closed."""
    from execution.execution_ledger import ExecutionLedger
    from execution.execution_lifecycle import ExecutionLifecycleStore
    from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
    from core.runtime_checkpoint import RuntimeCheckpointStore
    from core.operation_memory import OperationMemory

    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    calls = {"count": 0}

    class InterruptingAdapter:
        def is_available(self):
            return True

        def execute(self, request):
            calls["count"] += 1
            raise KeyboardInterrupt("simulated process interruption after broker-side effect")

    registry = BrokerRegistry()
    registry.register("fake", InterruptingAdapter())
    gateway = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    )

    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.REAL,
    )

    auth, admission, safety = _contracts()
    with pytest.raises(KeyboardInterrupt):
        gateway.execute(
            broker="fake",
            request_id="req-hard-interrupt",
            request=request,
            authorization=auth,
            admission=admission,
            safety=safety,
        )

    assert calls["count"] == 1
    assert ExecutionLedger(ledger_path).status("req-hard-interrupt") is ExecutionLedgerStatus.RESERVED
    assert ExecutionLifecycleStore(lifecycle_path).get("req-hard-interrupt").state is ExecutionLifecycleState.PENDING

    assessment = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    ).assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION

    class FailingReplayAdapter:
        def is_available(self):
            return True

        def execute(self, request):
            calls["count"] += 1
            raise AssertionError("replay must never reach broker")

    registry2 = BrokerRegistry()
    registry2.register("fake", FailingReplayAdapter())
    restarted = _real_gateway(
        BrokerAdapterGateway(registry2),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    )
    result = restarted.execute(
        broker="fake",
        request_id="req-hard-interrupt",
        request=request,
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    assert calls["count"] == 1


def test_real_external_id_bind_failure_is_non_replayable_after_restart(tmp_path, monkeypatch):
    class AcceptedAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-BIND-FAIL")

    adapter = AcceptedAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)

    def fail_bind(_request_id, _external_id):
        raise OSError("external identity persistence failed")

    monkeypatch.setattr(ledger, "bind_external_id", fail_bind)
    first = _real_gateway(
        BrokerAdapterGateway(registry), ledger, lifecycle
    ).execute(
        broker="fake",
        request_id="bind-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    durable_ledger = ExecutionLedger(ledger_path)
    assert durable_ledger.status("bind-failure") is ExecutionLedgerStatus.RESERVED
    assert durable_ledger.external_id("bind-failure") is None
    assert ExecutionLifecycleStore(lifecycle_path).get("bind-failure").state is ExecutionLifecycleState.UNKNOWN

    restarted = _real_gateway(
        BrokerAdapterGateway(registry),
        durable_ledger,
        ExecutionLifecycleStore(lifecycle_path),
    )
    retry = restarted.execute(
        broker="fake",
        request_id="bind-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert retry.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1


def test_real_lifecycle_persistence_failure_after_ledger_terminal_blocks_restart(tmp_path, monkeypatch):
    class AcceptedAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-LIFECYCLE-FAIL")

    adapter = AcceptedAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)

    original_put = lifecycle.put

    def fail_accepted(record):
        if record.state is ExecutionLifecycleState.ACCEPTED:
            raise OSError("lifecycle terminal persistence failed")
        return original_put(record)

    monkeypatch.setattr(lifecycle, "put", fail_accepted)
    first = _real_gateway(
        BrokerAdapterGateway(registry), ledger, lifecycle
    ).execute(
        broker="fake",
        request_id="lifecycle-terminal-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    durable_ledger = ExecutionLedger(ledger_path)
    assert durable_ledger.status("lifecycle-terminal-failure") is ExecutionLedgerStatus.ACCEPTED
    assert durable_ledger.external_id("lifecycle-terminal-failure") == "EXT-LIFECYCLE-FAIL"
    assert ExecutionLifecycleStore(lifecycle_path).get("lifecycle-terminal-failure").state is ExecutionLifecycleState.UNKNOWN

    restarted = _real_gateway(
        BrokerAdapterGateway(registry),
        durable_ledger,
        ExecutionLifecycleStore(lifecycle_path),
    )
    retry = restarted.execute(
        broker="fake",
        request_id="lifecycle-terminal-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert retry.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1


def test_recovery_worker_racing_execution_worker_never_replays_uncertain_request(tmp_path: Path):
    """A recovery query may resolve uncertainty while an execution worker races it; broker must not see a second dispatch."""
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("race-recovery-execution")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "race-recovery-execution",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    class QueryByRequestId:
        def query_order_by_request_id(self, request_id):
            return ExternalOrderObservation(
                "EXT-RACE",
                ExternalOrderStatus.EXECUTED,
                f"recovered for {request_id}",
            )

    recovery = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle),
        query_port=QueryByRequestId(),
    )

    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            raise AssertionError("uncertain request must never be replayed to broker")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    gateway = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
    )
    auth, admission, safety = _contracts()
    results = []
    errors = []

    def run_recovery():
        try:
            results.append(recovery.reconcile_request_by_request_id("race-recovery-execution"))
        except Exception as exc:
            errors.append(exc)

    def run_execution():
        try:
            results.append(
                gateway.execute(
                    broker="fake",
                    request_id="race-recovery-execution",
                    request=_request(),
                    authorization=auth,
                    admission=admission,
                    safety=safety,
                )
            )
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=run_recovery), Thread(target=run_execution)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert adapter.calls == 0
    assert ledger.external_id("race-recovery-execution") == "EXT-RACE"
    assert ledger.status("race-recovery-execution") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("race-recovery-execution").state is ExecutionLifecycleState.ACCEPTED

def test_request_id_recovery_is_strictly_read_only_and_never_dispatches(tmp_path):
    """Recovery by durable request identity may query, but must never place an order."""
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("request-id-read-only")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "request-id-read-only",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    class BrokerAdapterWithDangerousPlace:
        def __init__(self):
            self.query_calls = 0
            self.place_calls = 0

        def query_order_by_request_id(self, request_id):
            self.query_calls += 1
            assert request_id == "request-id-read-only"
            return ExternalOrderObservation(
                "EXT-READ-ONLY",
                ExternalOrderStatus.EXECUTED,
                "confirmed without submission",
            )

        def execute(self, _request):
            self.place_calls += 1
            raise AssertionError("request-id recovery must never dispatch")

        def is_available(self):
            return True

    broker = BrokerAdapterWithDangerousPlace()
    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(
            ledger=ledger,
            lifecycle=lifecycle,
        ),
        query_port=broker,
    )

    result = service.reconcile_request_by_request_id("request-id-read-only")

    assert result.reconciled is True
    assert result.status is ExternalOrderStatus.EXECUTED
    assert broker.query_calls == 1
    assert broker.place_calls == 0
    assert ExecutionLedger(ledger_path).external_id("request-id-read-only") == "EXT-READ-ONLY"
    assert ExecutionLedger(ledger_path).status("request-id-read-only") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLifecycleStore(lifecycle_path).get("request-id-read-only").state is ExecutionLifecycleState.ACCEPTED


def test_request_id_recovery_without_broker_capability_is_fail_closed_and_non_mutating(tmp_path):
    """A concrete adapter without request-id lookup cannot auto-reconcile a lost identity."""
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("request-id-no-capability")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "request-id-no-capability",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    class PlaceOnlyAdapter:
        def __init__(self):
            self.place_calls = 0

        def execute(self, _request):
            self.place_calls += 1
            raise AssertionError("recovery must not fall back to execution")

        def is_available(self):
            return True

    adapter = PlaceOnlyAdapter()
    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(
            ledger=ledger,
            lifecycle=lifecycle,
        ),
        query_port=adapter,
    )

    with pytest.raises(ValueError, match="somente-leitura por request_id"):
        service.reconcile_request_by_request_id("request-id-no-capability")

    assert adapter.place_calls == 0
    assert ExecutionLedger(ledger_path).external_id("request-id-no-capability") is None
    assert ExecutionLedger(ledger_path).status("request-id-no-capability") is ExecutionLedgerStatus.RESERVED
    assert ExecutionLifecycleStore(lifecycle_path).get("request-id-no-capability").state is ExecutionLifecycleState.UNKNOWN


def test_request_id_recovery_rejects_empty_external_identity_without_binding_or_dispatch(tmp_path):
    """A broker response without a concrete external identity cannot close the crash window."""
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("request-id-empty-external")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "request-id-empty-external",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    class QueryOnlyAdapter:
        def __init__(self):
            self.query_calls = 0
            self.place_calls = 0

        def query_order_by_request_id(self, request_id):
            self.query_calls += 1
            return ExternalOrderObservation(
                "",
                ExternalOrderStatus.EXECUTED,
                "broker returned no identity",
            )

        def execute(self, _request):
            self.place_calls += 1
            raise AssertionError("recovery must not fall back to execution")

        def is_available(self):
            return True

    adapter = QueryOnlyAdapter()
    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(
            ledger=ledger,
            lifecycle=lifecycle,
        ),
        query_port=adapter,
    )

    with pytest.raises(ValueError, match="não retornou external_id"):
        service.reconcile_request_by_request_id("request-id-empty-external")

    assert adapter.query_calls == 1
    assert adapter.place_calls == 0
    assert ExecutionLedger(ledger_path).external_id("request-id-empty-external") is None
    assert ExecutionLedger(ledger_path).status("request-id-empty-external") is ExecutionLedgerStatus.RESERVED
    assert ExecutionLifecycleStore(lifecycle_path).get("request-id-empty-external").state is ExecutionLifecycleState.UNKNOWN


def test_real_gateway_blocks_before_dispatch_when_durable_recovery_is_uncertain(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "must-not-dispatch", "EXT-NO-DISPATCH")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    ledger = ExecutionLedger(ledger_path)
    ledger.reserve("blocking-uncertain")
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(checkpoint_path),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    )
    auth, admission, safety = _contracts()

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
        recovery=recovery,
    ).execute(
        broker="fake",
        request_id="new-real-request",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ExecutionLedger(ledger_path).status("new-real-request") is None


def test_real_gateway_blocks_if_recovery_becomes_uncertain_after_reservation_without_dispatch(tmp_path: Path, monkeypatch):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "must-not-dispatch", "EXT-RACE-REAL")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    ledger = ExecutionLedger(ledger_path)
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(checkpoint_path),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    )
    original_assess = recovery.assess
    calls = {"count": 0}

    def racing_assess(*, ignore_request_id=None):
        calls["count"] += 1
        result = original_assess()
        if calls["count"] == 2:
            ledger.reserve("racing-real-worker")
        return result

    monkeypatch.setattr(recovery, "assess", racing_assess)
    auth, admission, safety = _contracts()

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ledger,
        ExecutionLifecycleStore(lifecycle_path),
        recovery=recovery,
    ).execute(
        broker="fake",
        request_id="guarded-real-request",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ledger.status("guarded-real-request") is ExecutionLedgerStatus.REJECTED
    assert ledger.status("racing-real-worker") is ExecutionLedgerStatus.RESERVED
    assert calls["count"] >= 2


def test_reconciliation_rejects_stale_observation_after_concurrent_terminalization(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("stale-reconciliation")
    ledger.bind_external_id("stale-reconciliation", "EXT-STALE")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "stale-reconciliation",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    coordinator = ExecutionReconciliationCoordinator(
        ledger=ExecutionLedger(ledger_path),
        lifecycle=ExecutionLifecycleStore(lifecycle_path),
    )
    holder_ready = threading.Event()
    worker_started = threading.Event()
    release = threading.Event()

    def terminalize_while_locked():
        with ledger.request_execution_lock("stale-reconciliation"):
            holder_ready.set()
            assert worker_started.wait(timeout=5)
            ledger._reconcile_locked("stale-reconciliation", executed=True)
            lifecycle.reconcile(
                "stale-reconciliation",
                ExecutionLifecycleState.ACCEPTED,
                updated_at=datetime.now(timezone.utc),
                message="execution completed while reconciliation waited",
            )
            release.wait(timeout=5)

    holder = threading.Thread(target=terminalize_while_locked)
    holder.start()
    assert holder_ready.wait(timeout=5)

    errors = []

    def reconcile_stale():
        worker_started.set()
        try:
            coordinator.reconcile(
                "stale-reconciliation",
                "EXT-STALE",
                ExternalOrderObservation(
                    "EXT-STALE",
                    ExternalOrderStatus.NOT_EXECUTED,
                    "stale negative observation",
                ),
            )
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=reconcile_stale)
    worker.start()
    assert worker_started.wait(timeout=5)

    # The reconciliation worker is concurrent with the execution holder.
    # On Windows the process-local durable-file gate may block it before the
    # per-request lock; on POSIX it may reach the request lock directly.
    # Either way, execution still owns the request while this assertion is made.
    assert worker.is_alive()

    release.set()
    holder.join(timeout=5)
    worker.join(timeout=5)

    assert len(errors) == 1
    assert "compatível" in str(errors[0]) or "terminal" in str(errors[0])
    assert ledger.status("stale-reconciliation") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("stale-reconciliation").state is ExecutionLifecycleState.ACCEPTED


def test_two_reconciliation_workers_converge_without_cross_store_corruption(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("two-recon-workers")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "two-recon-workers",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    class QueryByRequestId:
        def __init__(self):
            self.lock = Lock()
            self.calls = 0

        def query_order_by_request_id(self, request_id):
            with self.lock:
                self.calls += 1
            return ExternalOrderObservation(
                "EXT-TWO-RECON",
                ExternalOrderStatus.EXECUTED,
                f"confirmed for {request_id}",
            )

    query = QueryByRequestId()
    results = []
    errors = []
    services = [
        ExternalExecutionReconciliationService(
            coordinator=ExecutionReconciliationCoordinator(
                ledger=ExecutionLedger(ledger_path),
                lifecycle=ExecutionLifecycleStore(lifecycle_path),
            ),
            query_port=query,
        )
        for _ in range(2)
    ]

    def run(service):
        try:
            results.append(service.reconcile_request_by_request_id("two-recon-workers"))
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=run, args=(service,)) for service in services]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == 2
    assert query.calls == 2
    assert ExecutionLedger(ledger_path).external_id("two-recon-workers") == "EXT-TWO-RECON"
    assert ExecutionLedger(ledger_path).status("two-recon-workers") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLifecycleStore(lifecycle_path).get("two-recon-workers").state is ExecutionLifecycleState.ACCEPTED


def test_recovery_worker_racing_reconciliation_worker_never_reopens_terminal_state(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    ledger.reserve("recovery-vs-reconciliation")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "recovery-vs-reconciliation",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )

    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(checkpoint_path),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )

    class QueryByRequestId:
        def query_order_by_request_id(self, request_id):
            return ExternalOrderObservation(
                "EXT-RECOVERY-RACE",
                ExternalOrderStatus.EXECUTED,
                f"confirmed for {request_id}",
            )

    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(
            ledger=ExecutionLedger(ledger_path),
            lifecycle=ExecutionLifecycleStore(lifecycle_path),
        ),
        query_port=QueryByRequestId(),
    )
    results = []
    errors = []

    def run_recovery():
        try:
            results.append(recovery.assess())
        except Exception as exc:
            errors.append(exc)

    def run_reconciliation():
        try:
            results.append(service.reconcile_request_by_request_id("recovery-vs-reconciliation"))
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=run_recovery), Thread(target=run_reconciliation)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == 2
    assert ledger.external_id("recovery-vs-reconciliation") == "EXT-RECOVERY-RACE"
    assert ledger.status("recovery-vs-reconciliation") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("recovery-vs-reconciliation").state is ExecutionLifecycleState.ACCEPTED


def test_real_gateway_lifecycle_admission_failure_persists_rejected_in_both_authorities(tmp_path: Path, monkeypatch):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            raise AssertionError("broker must not be reached")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    auth, admission, safety = _contracts()

    original_put = lifecycle.put

    def fail_pending(record):
        if record.state is ExecutionLifecycleState.PENDING:
            raise OSError("pending lifecycle persistence failed")
        return original_put(record)

    monkeypatch.setattr(lifecycle, "put", fail_pending)

    result = _real_gateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
    ).execute(
        broker="fake",
        request_id="real-lifecycle-admission-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ledger.status("real-lifecycle-admission-failure") is ExecutionLedgerStatus.REJECTED
    assert lifecycle.get("real-lifecycle-admission-failure").state is ExecutionLifecycleState.REJECTED



def test_real_dispatch_and_reconciliation_share_request_lock_during_broker_call(tmp_path: Path):
    broker_entered = threading.Event()
    release_broker = threading.Event()

    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)

    class BlockingAdapter:
        def is_available(self):
            return True

        def execute(self, _request):
            # Simulate the broker/exchange assigning its identity while the
            # external call is still in flight. Reconciliation must wait on
            # the same request lock instead of racing this side effect.
            ledger.bind_external_id("real-lock-race", "EXT-LOCK-RACE")
            broker_entered.set()
            assert release_broker.wait(timeout=5)
            return ExecutionResult(True, "accepted", "EXT-LOCK-RACE")

    adapter = BlockingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    auth, admission, safety = _contracts()
    gateway = _real_gateway(BrokerAdapterGateway(registry), ledger, lifecycle)
    coordinator = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle)

    result_holder = []
    reconcile_holder = []

    def run_execution():
        result_holder.append(
            gateway.execute(
                broker="fake",
                request_id="real-lock-race",
                request=_request(),
                authorization=auth,
                admission=admission,
                safety=safety,
            )
        )

    def run_reconciliation():
        reconcile_holder.append(
            coordinator.reconcile(
                "real-lock-race",
                "EXT-LOCK-RACE",
                ExternalOrderObservation(
                    external_id="EXT-LOCK-RACE",
                    status=ExternalOrderStatus.EXECUTED,
                    message="broker confirmed execution",
                ),
            )
        )

    execution_thread = threading.Thread(target=run_execution)
    execution_thread.start()
    assert broker_entered.wait(timeout=5)

    reconciliation_thread = threading.Thread(target=run_reconciliation)
    reconciliation_thread.start()
    # The reconciliation worker must still be waiting while the broker call
    # owns the per-request lock.
    reconciliation_thread.join(timeout=0.2)
    assert reconciliation_thread.is_alive()

    release_broker.set()
    execution_thread.join(timeout=5)
    reconciliation_thread.join(timeout=5)

    assert not execution_thread.is_alive()
    assert not reconciliation_thread.is_alive()
    assert result_holder[0].status == RealGatewayStatus.ADMITTED
    assert len(reconcile_holder) == 1
    assert ExecutionLedger(ledger_path).status("real-lock-race") is ExecutionLedgerStatus.ACCEPTED
    assert ExecutionLifecycleStore(lifecycle_path).get("real-lock-race").state is ExecutionLifecycleState.ACCEPTED

def test_real_reconciliation_race_after_final_admission_check_never_dispatches(tmp_path: Path, monkeypatch):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-SHOULD-NOT-HAPPEN")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    auth, admission, safety = _contracts()
    gateway = _real_gateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
    )

    original_status = ledger.status
    calls = {"count": 0}

    def status_with_reconciliation(request_id):
        calls["count"] += 1
        status = original_status(request_id)
        if (
            request_id == "real-reconciliation-race"
            and status is ExecutionLedgerStatus.RESERVED
            and calls["count"] >= 2
        ):
            ledger.bind_external_id(request_id, "EXT-RECONCILED")
            ledger._reconcile_locked(request_id, executed=True)
            lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.ACCEPTED,
                updated_at=datetime.now(timezone.utc),
                message="reconciliado antes do broker",
            )
            return ExecutionLedgerStatus.RECONCILED_EXECUTED
        return status

    monkeypatch.setattr(ledger, "status", status_with_reconciliation)

    result = gateway.execute(
        broker="fake",
        request_id="real-reconciliation-race",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ExecutionLedger(ledger_path).status("real-reconciliation-race") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLifecycleStore(lifecycle_path).get("real-reconciliation-race").state is ExecutionLifecycleState.ACCEPTED


def test_kill_switch_activation_cannot_interleave_final_execution_window(tmp_path: Path):
    """The mutable kill switch cannot activate between final check and adapter dispatch."""
    from core.kill_switch import KillSwitch

    kill_switch = KillSwitch()
    entered = threading.Event()
    release = threading.Event()
    activation_finished = threading.Event()

    def activation_worker():
        kill_switch.activate("emergency")
        activation_finished.set()

    worker = Thread(target=activation_worker)
    with kill_switch.execution_window():
        assert kill_switch.allows_execution() is True
        entered.set()
        worker.start()
        assert entered.is_set()
        # Activation must wait while the final execution window is held.
        assert not activation_finished.wait(0.15)
        release.set()

    worker.join(timeout=2)
    assert not worker.is_alive()
    assert activation_finished.is_set()
    assert kill_switch.state.enabled is True
