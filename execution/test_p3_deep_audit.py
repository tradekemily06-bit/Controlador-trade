from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmissionBoundary
from core.p114_real_safety_gate import RealSafetyGate


def demo_request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO)


def real_request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def real_contracts():
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


def real_gateway(registry, ledger_path: Path):
    ledger = ExecutionLedger(ledger_path)
    lifecycle_path = ledger_path.with_name("lifecycle.json")
    checkpoint_path = ledger_path.with_name("checkpoint.json")
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(checkpoint_path),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle=lifecycle,
        recovery=recovery,
        kill_switch=KillSwitch(),
    )


def test_demo_executor_failure_persists_unknown_in_both_authorities_and_blocks_restart(tmp_path: Path):
    class BrokenExecutor:
        def execute(self, _request):
            raise TimeoutError("timeout")

    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    gateway = ExecutionGateway(
        BrokenExecutor(),
        KillSwitch(),
        ledger=ExecutionLedger(ledger_path),
        lifecycle=ExecutionLifecycleStore(lifecycle_path),
    )

    result = gateway.execute("req-deep-unknown", demo_request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ExecutionLedger(ledger_path).status("req-deep-unknown") is ExecutionLedgerStatus.UNKNOWN
    assert ExecutionLifecycleStore(lifecycle_path).get("req-deep-unknown").state is ExecutionLifecycleState.UNKNOWN

    restarted = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    ).assess()
    assert restarted.state is RecoveryState.REQUIRES_RECONCILIATION
    assert restarted.can_resume is False


def test_terminal_ledger_cannot_be_downgraded_to_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-terminal")
    ledger.mark_accepted("req-terminal")

    try:
        ledger.mark_unknown("req-terminal")
    except ValueError:
        pass
    else:
        raise AssertionError("terminal ACCEPTED must never be downgraded to UNKNOWN")

    assert ExecutionLedger(path).status("req-terminal") is ExecutionLedgerStatus.ACCEPTED


def test_real_accepted_request_cannot_be_replayed_after_restart(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-1")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "real-ledger.json"
    auth, admission, safety = real_contracts()

    first = real_gateway(registry, ledger_path)
    result = first.execute(
        broker="fake",
        request_id="req-real-terminal",
        request=real_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(ledger_path))
    replay = restarted.execute(
        broker="fake",
        request_id="req-real-terminal",
        request=real_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert replay.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1


def test_real_rejected_request_cannot_be_replayed_after_restart(tmp_path: Path):
    class RejectingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(False, "rejected", None)

    adapter = RejectingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "real-ledger.json"
    auth, admission, safety = real_contracts()

    first = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(ledger_path))
    result = first.execute(
        broker="fake",
        request_id="req-real-rejected",
        request=real_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 1

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(ledger_path))
    replay = restarted.execute(
        broker="fake",
        request_id="req-real-rejected",
        request=real_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert replay.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1


def test_real_unknown_restart_never_reaches_adapter(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            raise TimeoutError("unknown after dispatch")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    ledger_path = tmp_path / "real-ledger.json"
    auth, admission, safety = real_contracts()

    first = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(ledger_path))
    result = first.execute(
        broker="fake",
        request_id="req-real-unknown",
        request=real_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(ledger_path))
    retry = restarted.execute(
        broker="fake",
        request_id="req-real-unknown",
        request=real_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert retry.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1


def test_recovery_blocks_orphaned_terminal_ledger_after_restart(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(ledger_path)
    ledger.reserve("orphan")
    ledger.mark_accepted("orphan")

    assessment = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    ).assess()

    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False


def test_recovery_repairs_orphaned_terminal_ledger_without_dispatch(tmp_path: Path):
    from datetime import datetime, timezone

    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    ledger.reserve("orphan-repair")
    ledger.mark_accepted("orphan-repair")

    coordinator = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(lifecycle_path),
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    )
    assert coordinator.assess().state is RecoveryState.REQUIRES_RECONCILIATION

    repaired = coordinator.reconcile_terminal_lifecycle(
        "orphan-repair",
        updated_at=datetime.now(timezone.utc),
    )
    assert repaired.state is ExecutionLifecycleState.ACCEPTED
    assert coordinator.assess().state is RecoveryState.FRESH


def test_recovery_repairs_lifecycle_unknown_when_ledger_is_terminal(tmp_path: Path):
    from datetime import datetime, timezone

    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    ledger = ExecutionLedger(ledger_path)
    ledger.reserve("diverged")
    ledger.mark_accepted("diverged")
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    lifecycle.put(
        ExecutionLifecycleRecord(
            "diverged",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "simulated lifecycle persistence divergence",
        )
    )

    coordinator = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ExecutionLedger(ledger_path),
        memory=OperationMemory(),
    )
    assert coordinator.assess().state is RecoveryState.REQUIRES_RECONCILIATION

    repaired = coordinator.reconcile_terminal_lifecycle(
        "diverged",
        updated_at=datetime.now(timezone.utc),
    )
    assert repaired.state is ExecutionLifecycleState.ACCEPTED
    # Without a durable runtime checkpoint this is a clean FRESH start,
    # not SAFE_TO_RESUME. The important assertion is that the divergence is
    # gone and recovery no longer requires reconciliation.
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.FRESH
    assert assessment.can_resume is True
