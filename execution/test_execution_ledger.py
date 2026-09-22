import json

from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleStore
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
    first.mark_accepted("req-001")

    restored = ExecutionLedger(path)
    assert restored.contains("req-001") is True
    assert restored.records() == ("req-001",)


def test_gateway_rejects_duplicate_after_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path), lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle.json"))
    accepted = first.execute("req-001", request())
    assert accepted.status is GatewayStatus.ACCEPTED

    restored = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path), lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle.json"))
    duplicate = restored.execute("req-001", request())
    assert duplicate.status is GatewayStatus.DUPLICATE


def test_rejected_execution_is_not_recorded(tmp_path: Path):
    path = tmp_path / "ledger.json"
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path), lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle.json"))
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


def test_ledger_persists_external_id_across_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-ext")
    ledger.bind_external_id("req-ext", "broker-123")
    ledger.mark_accepted("req-ext")

    restored = ExecutionLedger(path)
    assert restored.external_id("req-ext") == "broker-123"


def test_ledger_rejects_external_id_collision(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1")
    ledger.reserve("req-2")
    ledger.bind_external_id("req-1", "broker-123")

    with pytest.raises(ValueError, match="outro request_id"):
        ledger.bind_external_id("req-2", "broker-123")


def test_unknown_cannot_be_promoted_to_terminal_without_reconciliation(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-unknown")
    ledger.mark_unknown("req-unknown")

    with pytest.raises(ValueError, match="UNKNOWN só pode sair por reconcile"):
        ledger.mark_accepted("req-unknown")
    with pytest.raises(ValueError, match="UNKNOWN só pode sair por reconcile"):
        ledger.mark_rejected("req-unknown")

    assert ledger.status("req-unknown") is ExecutionLedgerStatus.UNKNOWN


def test_reconcile_executed_requires_external_id(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-uncertain")
    ledger.mark_unknown("req-uncertain")

    with pytest.raises(ValueError, match="external_id durável"):
        ledger.reconcile("req-uncertain", executed=True)

    assert ledger.status("req-uncertain").value == "UNKNOWN"


def test_reconcile_executed_binds_external_id_atomically(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-uncertain")
    ledger.mark_unknown("req-uncertain")

    ledger.reconcile("req-uncertain", executed=True, external_id="broker-456")

    restored = ExecutionLedger(path)
    assert restored.status("req-uncertain").value == "RECONCILED_EXECUTED"
    assert restored.external_id("req-uncertain") == "broker-456"


def test_reconcile_cannot_steal_external_id(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1")
    ledger.mark_unknown("req-1")
    ledger.reserve("req-2")
    ledger.mark_unknown("req-2")
    ledger.bind_external_id("req-1", "broker-789")

    with pytest.raises(ValueError, match="outro request_id"):
        ledger.reconcile("req-2", executed=True, external_id="broker-789")


def test_legacy_status_only_ledger_remains_readable(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"req-1": "ACCEPTED"}', encoding="utf-8")

    ledger = ExecutionLedger(path)

    assert ledger.status("req-1").value == "ACCEPTED"
    assert ledger.external_id("req-1") is None


def test_unknown_cannot_be_promoted_by_record(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-record")
    ledger.mark_unknown("req-record")
    with pytest.raises(ValueError, match="estado UNKNOWN"):
        ledger.record("req-record")
    assert ledger.status("req-record") is ExecutionLedgerStatus.UNKNOWN


def test_ledger_rejects_impossible_external_id_state(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"bad": {"status": "REJECTED", "external_id": "broker-1"}}), encoding="utf-8")
    try:
        ExecutionLedger(path)
    except ValueError as exc:
        assert "external_id" in str(exc)
    else:
        raise AssertionError("ledger must reject external identity on non-executed terminal state")


def test_ledger_rejects_reconciled_executed_without_external_id(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"bad": "RECONCILED_EXECUTED"}), encoding="utf-8")
    try:
        ExecutionLedger(path)
    except ValueError as exc:
        assert "external_id" in str(exc)
    else:
        raise AssertionError("reconciled execution must have durable external identity")


def test_persisted_ledger_rejects_duplicate_external_id(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        '{"req-1":{"status":"ACCEPTED","external_id":"broker-dup"},'
        '"req-2":{"status":"ACCEPTED","external_id":"broker-dup"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="external_id duplicado"):
        ExecutionLedger(path)

# CI trigger: persisted-state audit coverage.

# CI trigger: continue end-to-end persisted-state audit.
