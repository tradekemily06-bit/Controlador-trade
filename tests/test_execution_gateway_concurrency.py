from __future__ import annotations

import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


class _CountingExecutor:
    def __init__(self, counter, counter_lock) -> None:
        self._counter = counter
        self._counter_lock = counter_lock

    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        with self._counter_lock:
            self._counter.value += 1
        return ExecutionResult(accepted=True, message="executado")


class _NoopExecutor:
    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        raise AssertionError("executor não deveria ser chamado")


def _gateway_worker(ledger_path: str, lifecycle_path: str, barrier, counter, counter_lock, results) -> None:
    gateway = ExecutionGateway(
        _CountingExecutor(counter, counter_lock),
        KillSwitch(),
        ledger=ExecutionLedger(ledger_path),
        lifecycle=ExecutionLifecycleStore(lifecycle_path),
    )
    barrier.wait(timeout=15)
    result = gateway.execute("same-request", _request())
    results.put(result.status.value)


def test_same_request_id_is_dispatched_at_most_once_across_processes(tmp_path: Path):
    ctx = multiprocessing.get_context("spawn")
    ledger_path = str(tmp_path / "ledger.json")
    lifecycle_path = str(tmp_path / "lifecycle.json")
    barrier = ctx.Barrier(2)
    counter = ctx.Value("i", 0)
    counter_lock = ctx.Lock()
    results = ctx.Queue()

    processes = [
        ctx.Process(
            target=_gateway_worker,
            args=(ledger_path, lifecycle_path, barrier, counter, counter_lock, results),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0

    statuses = sorted(results.get(timeout=5) for _ in processes)
    assert counter.value == 1
    assert statuses == [GatewayStatus.ACCEPTED.value, GatewayStatus.BLOCKED.value]

    ledger = ExecutionLedger(ledger_path)
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    assert ledger.status("same-request") is ExecutionLedgerStatus.ACCEPTED
    assert lifecycle.get("same-request").state is ExecutionLifecycleState.ACCEPTED


def test_lifecycle_conflict_cannot_leave_new_ledger_reservation_stranded(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    lifecycle.put(
        ExecutionLifecycleRecord(
            "conflict-request",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "existing cycle",
        )
    )

    ledger = ExecutionLedger(ledger_path)
    gateway = ExecutionGateway(
        _NoopExecutor(),
        KillSwitch(),
        ledger=ledger,
        lifecycle=lifecycle,
    )

    result = gateway.execute("conflict-request", _request())

    assert result.status is GatewayStatus.DUPLICATE
    assert ledger.status("conflict-request") is ExecutionLedgerStatus.UNKNOWN
