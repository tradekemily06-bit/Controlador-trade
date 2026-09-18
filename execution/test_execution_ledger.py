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
    first.reserve("req-001")
    first.mark_accepted("req-001", external_id="demo-001")

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
    with pytest.raises(ValueError, match="request_id"):
        ledger.contains(" ")


def test_ledger_publication_failure_preserves_previous_durable_state(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("stable")
    original_fsync = __import__("execution.execution_ledger", fromlist=["os"]).os.fsync

    def fail_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("execution.execution_ledger.os.fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated fsync failure"):
        ledger.mark_unknown("stable")

    assert ExecutionLedger(path).status("stable").value == "RESERVED"
    assert not path.with_name(".ledger.json.tmp").exists()
    monkeypatch.setattr("execution.execution_ledger.os.fsync", original_fsync)



def test_external_id_cannot_be_attached_to_two_requests(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-001")
    ledger.reserve("req-002")
    ledger.attach_external_id("req-001", "broker-001")

    with pytest.raises(ValueError, match="external_id já associado"):
        ledger.attach_external_id("req-002", "broker-001")


def test_duplicate_external_id_in_persisted_ledger_fails_closed(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text(
        '{"req-001":{"status":"ACCEPTED","external_id":"broker-001"},'
        '"req-002":{"status":"UNKNOWN","external_id":"broker-001"}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="external_id duplicado"):
        ExecutionLedger(path)


def test_terminal_transition_cannot_reuse_external_id(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-001")
    ledger.reserve("req-002")
    ledger.mark_accepted("req-001", external_id="broker-001")

    # req-002 cannot be given the same broker reference through the
    # mark_rejected transition either.
    with pytest.raises(ValueError, match="external_id já associado"):
        ledger.mark_rejected("req-002", external_id="broker-001")



def test_ledger_rejects_noncanonical_request_id_and_json_nonfinite_constants(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    with pytest.raises(ValueError, match="canônico"):
        ledger.reserve(" req-1 ")
    path.write_text('{"req-1": {"status": "RESERVED", "external_id": NaN}}', encoding="utf-8")
    with pytest.raises(ValueError, match="ledger de execução inválido"):
        ExecutionLedger(path)
