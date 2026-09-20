from __future__ import annotations

from multiprocessing import Process, Queue
from pathlib import Path

from core.models import Signal
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MarkerAdapter:
    supports_real_execution = True
    adapter_id = "marker-adapter"

    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def is_available(self) -> bool:
        return True

    def query_order_by_request_id(self, request_id):
        return ExternalOrderObservation(request_id, ExternalOrderStatus.EXECUTED, "confirmed")

    def query_order(self, external_id):
        return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "confirmed")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        with self.marker.open("a", encoding="utf-8") as handle:
            handle.write(request.request_id or "missing")
            handle.write("\n")
        return ExecutionResult(True, "accepted", "external-" + (request.request_id or "missing"))


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest(
        "TEST",
        Signal.COMPRA,
        1.0,
        60,
        ExecutionMode.REAL,
        request_id=request_id,
    )


def _authorization() -> RealExecutionAuthorization:
    return RealExecutionAuthorization(
        "auth", "audit", "fake", "marker-adapter", True, True
    )


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="admission",
        audit_id="audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="fake",
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )


def _worker(root: str, marker: str, request_id: str, queue: Queue) -> None:
    registry = BrokerRegistry()
    registry.register("fake", MarkerAdapter(Path(marker)))
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(Path(root) / "ledger.json"),
        ExecutionLifecycleStore(Path(root) / "lifecycle.json"),
    )
    result = gateway.execute(
        broker="fake",
        request_id=request_id,
        request=_request(request_id),
        authorization=_authorization(),
        admission=_admission(),
        safety=_safety(),
    )
    queue.put(result.status)


def test_real_gateway_same_request_is_single_dispatch_across_processes(tmp_path):
    marker = tmp_path / "dispatches.txt"
    queue = Queue()
    processes = [
        Process(
            target=_worker,
            args=(str(tmp_path), str(marker), "same-real-request", queue),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)

    assert all(process.exitcode == 0 for process in processes)
    statuses = [queue.get(timeout=5) for _ in processes]
    assert statuses.count(RealGatewayStatus.ADMITTED) == 1
    assert statuses.count(RealGatewayStatus.BLOCKED) == 1

    dispatches = marker.read_text(encoding="utf-8").splitlines()
    assert dispatches == ["same-real-request"]

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    assert ledger.status("same-real-request").value == "ACCEPTED"
    assert lifecycle.get("same-real-request").state.value == "ACCEPTED"
