from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def _request(*, risk_state_fingerprint: str | None = None) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        risk_state_fingerprint=risk_state_fingerprint,
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


def test_risk_state_change_after_reservation_blocks_dispatch_and_marks_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    executor = PaperExecutor()
    expected = "a" * 64
    changed = "b" * 64
    calls = 0

    def risk_provider() -> str:
        nonlocal calls
        calls += 1
        # First check sees the state captured by the decision; the second
        # check observes a changed authoritative state after reservation.
        return expected if calls == 1 else changed

    gateway = ExecutionGateway(
        executor,
        KillSwitch(),
        ledger=ExecutionLedger(path),
        risk_state_fingerprint_provider=risk_provider,
    )

    result = gateway.execute("risk-race", _request(risk_state_fingerprint=expected))

    assert result.status is GatewayStatus.BLOCKED
    assert "estado de risco mudou" in result.message
    assert calls >= 2
    assert executor.executions() == ()
    assert ExecutionLedger(path).status("risk-race") is ExecutionLedgerStatus.UNKNOWN
