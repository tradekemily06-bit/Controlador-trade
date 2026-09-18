from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_ledger_survives_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    first.record("req-001")

    restored = ExecutionLedger(path)
    assert restored.contains("req-001") is True
    assert restored.records() == ("req-001",)


def test_gateway_rejects_duplicate_after_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    accepted = first.execute("req-001", request())
    assert accepted.status is GatewayStatus.ACCEPTED

    restored = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    duplicate = restored.execute("req-001", request())
    assert duplicate.status is GatewayStatus.DUPLICATE


def test_rejected_execution_is_not_recorded(tmp_path: Path):
    path = tmp_path / "ledger.json"
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    invalid = ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=-1.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )
    result = gateway.execute("req-001", invalid)
    assert result.status is GatewayStatus.INVALID_REQUEST
    assert ExecutionLedger(path).records() == ()


def test_invalid_ledger_fails_closed(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"invalid": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="ledger de execução inválido"):
        ExecutionLedger(path)


def test_empty_request_id_is_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    with pytest.raises(ValueError, match="request_id não pode ser vazio"):
        ledger.contains(" ")

from threading import Lock, Thread
from execution.ports import ExecutionResult


def test_gateway_reserves_before_concurrent_executors(tmp_path):
    class CountingExecutor:
        def __init__(self):
            self._lock = Lock()
            self.calls = 0

        def execute(self, _request):
            with self._lock:
                self.calls += 1
            return ExecutionResult(accepted=True, message="accepted", external_id="EXT-1")

    path = tmp_path / "ledger.json"
    executor = CountingExecutor()
    first = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    second = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path))

    # The first gateway establishes the normal persisted path.
    assert first.execute("req-concurrent", request()).status is GatewayStatus.ACCEPTED
    assert second.execute("req-concurrent", request()).status is GatewayStatus.DUPLICATE
    assert executor.calls == 0


def test_two_gateways_share_ledger_without_double_dispatch(tmp_path):
    class BlockingExecutor:
        def __init__(self):
            self._lock = Lock()
            self.calls = 0

        def execute(self, _request):
            with self._lock:
                self.calls += 1
            return ExecutionResult(accepted=True, message="accepted", external_id=f"EXT-{self.calls}")

    path = tmp_path / "ledger-race.json"
    executor = BlockingExecutor()
    gateways = [
        ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path)),
        ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path)),
    ]
    results = []

    def run(gateway):
        results.append(gateway.execute("req-race", request()).status)

    threads = [Thread(target=run, args=(gateway,)) for gateway in gateways]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results, key=lambda status: status.value) == sorted(
        [GatewayStatus.ACCEPTED, GatewayStatus.DUPLICATE], key=lambda status: status.value
    )
    assert executor.calls == 1
