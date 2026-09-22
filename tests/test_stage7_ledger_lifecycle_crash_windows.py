from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

from core.kill_switch import KillSwitch
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.gateway import ExecutionGateway
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest(symbol="TEST", signal=Signal.COMPRA, amount=10.0, duration_seconds=60, mode=ExecutionMode.DEMO, request_id=request_id)


class CrashAfterDispatchExecutor:
    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        os._exit(71)


class CrashAfterLedgerAcceptedLifecycle(ExecutionLifecycleStore):
    def put(self, record: ExecutionLifecycleRecord) -> None:
        if record.state is ExecutionLifecycleState.ACCEPTED:
            os._exit(72)
        super().put(record)


class CrashAfterLedgerRejectedLifecycle(ExecutionLifecycleStore):
    def put(self, record: ExecutionLifecycleRecord) -> None:
        if record.state is ExecutionLifecycleState.REJECTED:
            os._exit(73)
        super().put(record)


class AcceptingExecutor:
    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(True, "accepted", "external-crash-window")


class RejectingExecutor:
    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(False, "rejected", None)


def _recovery(tmp_path: Path) -> RecoveryCoordinator:
    return RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    )


def _dispatch_crash_worker(ledger_path: str, lifecycle_path: str) -> None:
    gateway = ExecutionGateway(CrashAfterDispatchExecutor(), KillSwitch(), ledger=ExecutionLedger(Path(ledger_path)), lifecycle=ExecutionLifecycleStore(Path(lifecycle_path)))
    gateway.execute("crash-dispatch", _request("crash-dispatch"))


def _accepted_post_ledger_crash_worker(ledger_path: str, lifecycle_path: str) -> None:
    gateway = ExecutionGateway(AcceptingExecutor(), KillSwitch(), ledger=ExecutionLedger(Path(ledger_path)), lifecycle=CrashAfterLedgerAcceptedLifecycle(Path(lifecycle_path)))
    gateway.execute("crash-accepted", _request("crash-accepted"))


def _rejected_post_ledger_crash_worker(ledger_path: str, lifecycle_path: str) -> None:
    gateway = ExecutionGateway(RejectingExecutor(), KillSwitch(), ledger=ExecutionLedger(Path(ledger_path)), lifecycle=CrashAfterLedgerRejectedLifecycle(Path(lifecycle_path)))
    gateway.execute("crash-rejected", _request("crash-rejected"))


def _assert_recovery_blocked(tmp_path: Path) -> None:
    assessment = _recovery(tmp_path).assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False


def test_process_death_after_dispatch_before_persistence_blocks_recovery(tmp_path: Path):
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_dispatch_crash_worker, args=(str(tmp_path / "ledger.json"), str(tmp_path / "lifecycle.json")))
    process.start()
    process.join(timeout=15)
    assert process.exitcode == 71
    assert ExecutionLedger(tmp_path / "ledger.json").status("crash-dispatch") is ExecutionLedgerStatus.RESERVED
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("crash-dispatch")
    assert lifecycle is not None
    assert lifecycle.state is ExecutionLifecycleState.PENDING
    _assert_recovery_blocked(tmp_path)


def test_process_death_after_ledger_accept_before_lifecycle_blocks_recovery(tmp_path: Path):
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_accepted_post_ledger_crash_worker, args=(str(tmp_path / "ledger.json"), str(tmp_path / "lifecycle.json")))
    process.start()
    process.join(timeout=15)
    assert process.exitcode == 72
    assert ExecutionLedger(tmp_path / "ledger.json").status("crash-accepted") is ExecutionLedgerStatus.ACCEPTED
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("crash-accepted")
    assert lifecycle is not None
    assert lifecycle.state is ExecutionLifecycleState.PENDING
    _assert_recovery_blocked(tmp_path)


def test_process_death_after_ledger_reject_before_lifecycle_blocks_recovery(tmp_path: Path):
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_rejected_post_ledger_crash_worker, args=(str(tmp_path / "ledger.json"), str(tmp_path / "lifecycle.json")))
    process.start()
    process.join(timeout=15)
    assert process.exitcode == 73
    assert ExecutionLedger(tmp_path / "ledger.json").status("crash-rejected") is ExecutionLedgerStatus.REJECTED
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("crash-rejected")
    assert lifecycle is not None
    assert lifecycle.state is ExecutionLifecycleState.PENDING
    _assert_recovery_blocked(tmp_path)
