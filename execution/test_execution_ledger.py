from concurrent.futures import ThreadPoolExecutor
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


def test_concurrent_gateways_only_one_worker_can_reserve_same_request_id(tmp_path: Path):
    path = tmp_path / "ledger.json"
    gateways = [
        ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
        for _ in range(16)
    ]

    def attempt(index: int):
        return gateways[index].execute("same-concurrent-id", request())

    with ThreadPoolExecutor(max_workers=len(gateways)) as pool:
        results = list(pool.map(attempt, range(len(gateways))))

    accepted = [result for result in results if result.status is GatewayStatus.ACCEPTED]
    duplicates = [result for result in results if result.status is GatewayStatus.DUPLICATE]
    blocked_or_uncertain = [
        result for result in results
        if result.status not in (GatewayStatus.ACCEPTED, GatewayStatus.DUPLICATE)
    ]

    assert len(accepted) == 1
    assert len(duplicates) == 15
    assert blocked_or_uncertain == []
    assert ExecutionLedger(path).records() == ("same-concurrent-id",)
