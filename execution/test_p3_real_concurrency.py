from threading import Lock, Thread
from pathlib import Path
from datetime import datetime, timezone
import pytest

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
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
        RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path)),
        RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path)),
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
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)

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

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
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
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)

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

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
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
    gateway = RealExecutionGateway(
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

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
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

    result = RealExecutionGateway(
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

    result = RealExecutionGateway(
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

    result = RealExecutionGateway(
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

    result = RealExecutionGateway(
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

    result = RealExecutionGateway(
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

    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
    )

    with pytest.raises(ValueError, match="external_id durável"):
        gateway.reconcile_unknown("reconcile-cross-store", executed=True)

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
    first = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle).execute(
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
    assert ExecutionLifecycleStore(lifecycle_path).get("pending-before-reserve").state is ExecutionLifecycleState.PENDING

    from core.operation_memory import OperationMemory
    from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
    from core.runtime_checkpoint import RuntimeCheckpointStore

    assessment = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    ).assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION

    restarted = RealExecutionGateway(
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
    assert retry.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


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
        RealExecutionGateway(
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
