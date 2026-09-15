from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_concurrent_gateways_only_one_worker_can_reserve_same_request_id(tmp_path: Path):
    path = tmp_path / "ledger.json"
    gateways = [
        ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
        for _ in range(16)
    ]

    def attempt(index: int):
        return gateways[index].execute("same-concurrent-id", _request())

    with ThreadPoolExecutor(max_workers=len(gateways)) as pool:
        results = list(pool.map(attempt, range(len(gateways))))

    accepted = [result for result in results if result.status is GatewayStatus.ACCEPTED]
    duplicates = [result for result in results if result.status is GatewayStatus.DUPLICATE]

    assert len(accepted) == 1
    assert len(duplicates) == 15
    assert ExecutionLedger(path).records() == ("same-concurrent-id",)
