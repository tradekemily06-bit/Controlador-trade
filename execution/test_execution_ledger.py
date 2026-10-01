from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


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


class RaisingExecutor:
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise RuntimeError("simulated post-admission failure")


def test_executor_failure_becomes_durable_unknown_and_blocks_restart_replay(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionGateway(RaisingExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    result = first.execute("req-crash", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ExecutionLedger(path).status("req-crash") is ExecutionLedgerStatus.UNKNOWN

    restored = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    duplicate = restored.execute("req-crash", request())
    assert duplicate.status is GatewayStatus.DUPLICATE


def test_invalid_ledger_fails_closed(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"invalid": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="ledger de execução inválido"):
        ExecutionLedger(path)


def test_empty_request_id_is_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    with pytest.raises(ValueError, match="request_id não pode ser vazio"):
        ledger.contains(" ")


def test_cycle_and_external_identity_survive_restart(tmp_path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    first.reserve("req-id", cycle_id="cycle-id")
    first.bind_external_id("req-id", "123")
    first.mark_accepted("req-id")

    restored = ExecutionLedger(path)
    record = restored.record_for("req-id")
    assert record is not None
    assert record.status is ExecutionLedgerStatus.ACCEPTED
    assert record.cycle_id == "cycle-id"
    assert record.external_id == "123"


def test_external_id_cannot_be_bound_to_two_requests(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1", cycle_id="cycle-1")
    ledger.reserve("req-2", cycle_id="cycle-2")
    ledger.bind_external_id("req-1", "123")
    with pytest.raises(ValueError, match="outro request_id"):
        ledger.bind_external_id("req-2", "123")


def test_find_by_cycle_id_is_durable_identity_lookup(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1", cycle_id="cycle-1")
    ledger.bind_external_id("req-1", "123")
    assert ledger.find_by_cycle_id("cycle-1")[0][0] == "req-1"


def test_cycle_id_is_required_for_canonical_reservation_when_supplied(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    with pytest.raises(ValueError, match="cycle_id"):
        ledger.reserve("req-1", cycle_id="")


def test_cycle_id_cannot_be_reserved_twice(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1", cycle_id="cycle-1")
    with pytest.raises(ValueError, match="cycle_id já possui"):
        ledger.reserve("req-2", cycle_id="cycle-1")
