from __future__ import annotations

import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from core.operational_safety_store import OperationalSafetyStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


def _request(request_id: str = "same-request") -> ExecutionRequest:
    return ExecutionRequest(symbol="BTCUSD", signal=Signal.COMPRA, amount=10.0, duration_seconds=60, mode=ExecutionMode.DEMO, request_id=request_id)


class _CountingExecutor:
    def __init__(self, counter, counter_lock) -> None:
        self._counter, self._counter_lock = counter, counter_lock

    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        with self._counter_lock:
            self._counter.value += 1
        return ExecutionResult(accepted=True, message="executado")


class _StateChangingExecutor:
    def __init__(self, counter, counter_lock, safety_path: str) -> None:
        self._counter, self._counter_lock, self._safety_path = counter, counter_lock, safety_path

    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        with self._counter_lock:
            self._counter.value += 1
            first = self._counter.value == 1
        if first:
            OperationalSafetyStore(self._safety_path).set_kill_switch(
                enabled=True, reason="estado operacional alterado durante concorrência"
            )
        return ExecutionResult(accepted=True, message="executado")


class _NoopExecutor:
    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        raise AssertionError("executor não deveria ser chamado")


def _gateway_worker(ledger_path: str, lifecycle_path: str, barrier, counter, counter_lock, results) -> None:
    gateway = ExecutionGateway(_CountingExecutor(counter, counter_lock), KillSwitch(), ledger=ExecutionLedger(ledger_path), lifecycle=ExecutionLifecycleStore(lifecycle_path))
    barrier.wait(timeout=15)
    results.put(gateway.execute("same-request", _request()).status.value)


def _different_request_worker(ledger_path: str, lifecycle_path: str, safety_path: str, barrier, counter, counter_lock, results, request_id: str) -> None:
    gateway = ExecutionGateway(
        _StateChangingExecutor(counter, counter_lock, safety_path), KillSwitch(),
        ledger=ExecutionLedger(ledger_path), lifecycle=ExecutionLifecycleStore(lifecycle_path),
        safety_store=OperationalSafetyStore(safety_path),
    )
    barrier.wait(timeout=15)
    results.put((request_id, gateway.execute(request_id, _request()).status.value))


def test_same_request_id_is_dispatched_at_most_once_across_processes(tmp_path: Path):
    ctx = multiprocessing.get_context("spawn")
    ledger_path, lifecycle_path = str(tmp_path / "ledger.json"), str(tmp_path / "lifecycle.json")
    barrier, counter, counter_lock, results = ctx.Barrier(2), ctx.Value("i", 0), ctx.Lock(), ctx.Queue()
    processes = [ctx.Process(target=_gateway_worker, args=(ledger_path, lifecycle_path, barrier, counter, counter_lock, results)) for _ in range(2)]
    for process in processes: process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    assert sorted(results.get(timeout=5) for _ in processes) == [GatewayStatus.ACCEPTED.value, GatewayStatus.BLOCKED.value]
    assert counter.value == 1
    assert ExecutionLedger(ledger_path).status("same-request") is ExecutionLedgerStatus.ACCEPTED
    assert ExecutionLifecycleStore(lifecycle_path).get("same-request").state is ExecutionLifecycleState.ACCEPTED


def test_different_request_ids_recheck_shared_safety_state_inside_dispatch_lock(tmp_path: Path):
    """Prove cross-process TOCTOU protection, not only duplicate-ID idempotency."""
    ctx = multiprocessing.get_context("spawn")
    ledger_path, lifecycle_path, safety_path = (str(tmp_path / name) for name in ("ledger.json", "lifecycle.json", "safety.json"))
    OperationalSafetyStore(safety_path).set_kill_switch(enabled=False)
    barrier, counter, counter_lock, results = ctx.Barrier(2), ctx.Value("i", 0), ctx.Lock(), ctx.Queue()
    ids = ("request-a", "request-b")
    processes = [ctx.Process(target=_different_request_worker, args=(ledger_path, lifecycle_path, safety_path, barrier, counter, counter_lock, results, request_id)) for request_id in ids]
    for process in processes: process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    outcomes = dict(results.get(timeout=5) for _ in processes)
    assert counter.value == 1
    assert sorted(outcomes.values()) == [GatewayStatus.ACCEPTED.value, GatewayStatus.BLOCKED.value]
    _audit, state = OperationalSafetyStore(safety_path).load()
    assert state.enabled is True


def test_lifecycle_conflict_cannot_leave_new_ledger_reservation_stranded(tmp_path: Path):
    ledger_path, lifecycle_path = tmp_path / "ledger.json", tmp_path / "lifecycle.json"
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    lifecycle.put(ExecutionLifecycleRecord("conflict-request", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc), "existing cycle"))
    ledger = ExecutionLedger(ledger_path)
    gateway = ExecutionGateway(_NoopExecutor(), KillSwitch(), ledger=ledger, lifecycle=lifecycle)
    result = gateway.execute("conflict-request", _request("conflict-request"))
    assert result.status is GatewayStatus.DUPLICATE
    assert ledger.status("conflict-request") is ExecutionLedgerStatus.UNKNOWN
