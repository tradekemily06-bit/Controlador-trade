from core.kill_switch import KillSwitch
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleStore, ExecutionLifecycleState
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from core.models import Signal


class AcceptingExecutor:
    def execute(self, request):
        return ExecutionResult(True, "accepted", "PAPER-TEST")


class RejectingExecutor:
    def execute(self, request):
        return ExecutionResult(False, "rejected", None)


class FailOnSecondLifecycleWrite(ExecutionLifecycleStore):
    def __init__(self, path):
        super().__init__(path)
        self.write_calls = 0

    def put(self, record):
        self.write_calls += 1
        if self.write_calls == 2:
            raise OSError("simulated lifecycle persistence failure")
        return super().put(record)


def request(request_id):
    return ExecutionRequest(symbol="TEST", signal=Signal.COMPRA, amount=10.0, duration_seconds=60,
                            mode=ExecutionMode.DEMO, request_id=request_id)


def recovery(tmp_path):
    return RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    )


def test_accepted_ledger_with_failed_lifecycle_persistence_blocks_recovery(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = FailOnSecondLifecycleWrite(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(AcceptingExecutor(), KillSwitch(), ledger=ledger, lifecycle=lifecycle)

    result = gateway.execute("cross-accepted", request("cross-accepted"))

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("cross-accepted") is ExecutionLedgerStatus.ACCEPTED
    assert ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("cross-accepted").state is ExecutionLifecycleState.UNKNOWN
    assessed = recovery(tmp_path).assess()
    assert assessed.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessed.can_resume is False


def test_rejected_ledger_with_failed_lifecycle_persistence_blocks_recovery(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = FailOnSecondLifecycleWrite(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(RejectingExecutor(), KillSwitch(), ledger=ledger, lifecycle=lifecycle)

    result = gateway.execute("cross-rejected", request("cross-rejected"))

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("cross-rejected") is ExecutionLedgerStatus.REJECTED
    assert ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("cross-rejected").state is ExecutionLifecycleState.UNKNOWN
    assessed = recovery(tmp_path).assess()
    assert assessed.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessed.can_resume is False
