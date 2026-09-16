from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class SlowFileExecutor:
    def __init__(self, log_path: str, label: str):
        self.log_path = Path(log_path)
        self.label = label

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"start-{self.label}\n")
            handle.flush()
        time.sleep(0.1)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"end-{self.label}\n")
            handle.flush()
        return ExecutionResult(True, "ok", f"external-{self.label}")


def _worker(root: str, log_path: str, label: str, result_path: str) -> None:
    ledger = ExecutionLedger(Path(root) / "ledger.json")
    gateway = ExecutionGateway(SlowFileExecutor(log_path, label), KillSwitch(), ledger=ledger)
    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id=f"req-{label}",
    )
    result = gateway.execute(request.request_id, request)
    Path(result_path).write_text(result.status.value, encoding="utf-8")


def test_shared_ledger_serializes_cross_process_dispatch(tmp_path):
    log_path = tmp_path / "dispatch.log"
    result_a = tmp_path / "result-a.txt"
    result_b = tmp_path / "result-b.txt"
    context = multiprocessing.get_context("spawn")
    process_a = context.Process(target=_worker, args=(str(tmp_path), str(log_path), "a", str(result_a)))
    process_b = context.Process(target=_worker, args=(str(tmp_path), str(log_path), "b", str(result_b)))

    process_a.start()
    process_b.start()
    process_a.join(10)
    process_b.join(10)

    assert process_a.exitcode == 0
    assert process_b.exitcode == 0
    assert result_a.read_text(encoding="utf-8") == GatewayStatus.ACCEPTED.value
    assert result_b.read_text(encoding="utf-8") == GatewayStatus.ACCEPTED.value

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("start-")
    assert lines[1] == lines[0].replace("start-", "end-")
    assert lines[2].startswith("start-")
    assert lines[3] == lines[2].replace("start-", "end-")
