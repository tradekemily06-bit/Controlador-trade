from __future__ import annotations

import multiprocessing
from pathlib import Path
import time

from core.global_operational_barrier import GlobalOperationalBarrier
from core.test_p111_p119_real_release import (
    _admission,
    _authorization,
    _request,
    _risk_state,
    _safety,
    _snapshot,
    FakeRealSafetyProvider,
    FakeRiskStateProvider,
)
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class SlowLoggingAdapter:
    def __init__(self, log_path: str) -> None:
        self.log_path = Path(log_path)

    def is_available(self) -> bool:
        return True

    def execute(self, request) -> ExecutionResult:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{request.request_id}:start\n")
        time.sleep(0.15)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{request.request_id}:end\n")
        return ExecutionResult(True, "accepted", f"external-{request.request_id}")


def _worker(ledger_path: str, log_path: str, request_id: str, queue) -> None:
    registry = BrokerRegistry()
    registry.register("fake", SlowLoggingAdapter(log_path), adapter_id="fake-adapter")
    auth = _authorization(request_id=request_id)
    safety = _safety()
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        FakeRiskStateProvider(_risk_state()),
        FakeRealSafetyProvider(safety),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )
    request = _request(request_id=request_id)
    result = gateway.execute(
        broker="fake",
        request_id=request_id,
        request=request,
        authorization=auth,
        admission=_admission(request_id=request_id, auth=auth),
        safety=safety,
        snapshot=_snapshot(),
    )
    queue.put((request_id, result.status))


def test_real_dispatch_is_serialized_across_processes(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    log_path = tmp_path / "dispatch.log"
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(target=_worker, args=(str(ledger_path), str(log_path), request_id, queue))
        for request_id in ("real-concurrent-a", "real-concurrent-b")
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0

    results = {queue.get(timeout=2) for _ in processes}
    assert results == {
        ("real-concurrent-a", RealGatewayStatus.ADMITTED),
        ("real-concurrent-b", RealGatewayStatus.ADMITTED),
    }

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert lines[0].endswith(":start")
    assert lines[1].endswith(":end")
    assert lines[2].endswith(":start")
    assert lines[3].endswith(":end")
    assert lines[0].split(":")[0] == lines[1].split(":")[0]
    assert lines[2].split(":")[0] == lines[3].split(":")[0]

    ledger = ExecutionLedger(ledger_path)
    assert ledger.status("real-concurrent-a") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.status("real-concurrent-b") is ExecutionLedgerStatus.ACCEPTED


def test_same_request_id_concurrent_processes_can_dispatch_at_most_once(tmp_path: Path) -> None:
    ledger_path = tmp_path / "same-request-ledger.json"
    log_path = tmp_path / "same-request.log"
    request_id = "real-same-request"
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(target=_worker, args=(str(ledger_path), str(log_path), request_id, queue))
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0

    results = [queue.get(timeout=2)[1] for _ in processes]
    assert sorted(results) == sorted([RealGatewayStatus.ADMITTED, RealGatewayStatus.BLOCKED])

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines == [f"{request_id}:start", f"{request_id}:end"]
    ledger = ExecutionLedger(ledger_path)
    assert ledger.status(request_id) is ExecutionLedgerStatus.ACCEPTED
