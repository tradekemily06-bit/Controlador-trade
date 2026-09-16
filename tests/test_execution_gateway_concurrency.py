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


class _SafetyChangingExecutor:
    def __init__(self, request_id: str, safety_path: str, entered, release, counter, counter_lock) -> None:
        self._request_id = request_id
        self._safety_path = safety_path
        self._entered = entered
        self._release = release
        self._counter = counter
        self._counter_lock = counter_lock

    def execute(self, _request: ExecutionRequest) -> ExecutionResult:
        with self._counter_lock:
            self._counter.value += 1
        if self._request_id == "request-a":
            OperationalSafetyStore(self._safety_path).set_kill_switch(enabled=True, reason="teste de mudança durante dispatch")
            self._entered.set()
            if not self._release.wait(15):
                raise RuntimeError("barreira de teste não liberou o primeiro executor")
        return ExecutionResult(accepted=True, message="executado")


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


def _different_request_worker(ledger_path: str, lifecycle_path: str, safety_path: str, barrier, entered, release, counter, counter_lock, results, request_id: str) -> None:
    safety_store = OperationalSafetyStore(safety_path)
    gateway = ExecutionGateway(
        _SafetyChangingExecutor(request_id, safety_path, entered, release, counter, counter_lock),
        KillSwitch(),
        ledger=ExecutionLedger(ledger_path),
        lifecycle=ExecutionLifecycleStore(lifecycle_path),
        safety_store=safety_store,
    )
    barrier.wait(timeout=15)
    result = gateway.execute(request_id, _request())
    results.put((request_id, result.status.value))


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


def test_different_request_ids_are_serialized_with_final_safety_recheck(tmp_path: Path):
    """A shared safety change during request A's side effect must block request B."""
    ctx = multiprocessing.get_context("spawn")
    ledger_path = str(tmp_path / "ledger.json")
    lifecycle_path = str(tmp_path / "lifecycle.json")
    safety_path = str(tmp_path / "safety.json")
    entered = ctx.Event()
    release = ctx.Event()
    counter = ctx.Value("i", 0)
    counter_lock = ctx.Lock()
    results = ctx.Queue()

    request_a = ctx.Process(
        target=_different_request_worker,
        args=(ledger_path, lifecycle_path, safety_path, None, entered, release, counter, counter_lock, results, "request-a"),
    )
    request_a.start()

    assert entered.wait(15), "request-a não chegou ao executor; teste não exercitou a janela de TOCTOU"

    request_b = ctx.Process(
        target=_different_request_worker,
        args=(ledger_path, lifecycle_path, safety_path, None, entered, release, counter, counter_lock, results, "request-b"),
    )
    request_b.start()

    # request-a already owns the shared dispatch lock while request-b attempts
    # the same critical section with a different request_id.
    release.set()

    for process in (request_a, request_b):
        process.join(20)
        assert process.exitcode == 0

    outcomes = dict(results.get(timeout=5) for _ in (request_a, request_b))
    assert outcomes["request-a"] == GatewayStatus.ACCEPTED.value
    assert outcomes["request-b"] == GatewayStatus.BLOCKED.value
    assert counter.value == 1

    ledger = ExecutionLedger(ledger_path)
    assert ledger.status("request-a") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.status("request-b") is ExecutionLedgerStatus.UNKNOWN


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
