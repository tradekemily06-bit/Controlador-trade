from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
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


def test_accepted_external_id_survives_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-ext")
    ledger.mark_accepted("req-ext", external_id="broker-123")

    restored = ExecutionLedger(path)
    assert restored.status("req-ext").value == "ACCEPTED"
    assert restored.external_id("req-ext") == "broker-123"


def test_legacy_status_only_format_remains_readable(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"legacy": "ACCEPTED"}', encoding="utf-8")
    ledger = ExecutionLedger(path)
    assert ledger.status("legacy").value == "ACCEPTED"
    assert ledger.external_id("legacy") is None


def test_external_id_cannot_be_reused_for_another_request(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-a")
    ledger.mark_accepted("req-a", external_id="broker-123")
    ledger.reserve("req-b")
    with pytest.raises(ValueError, match="external_id"):
        ledger.mark_accepted("req-b", external_id="broker-123")


def test_demo_record_does_not_require_external_reference_after_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.record("demo-1")

    restored = ExecutionLedger(path)
    assert restored.status("demo-1").value == "ACCEPTED"
    assert restored.external_reference_required("demo-1") is False
    assert restored.external_id("demo-1") is None


def test_real_acceptance_requires_external_reference(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("real-1")
    ledger.mark_accepted("real-1", external_id="broker-1")
    assert ledger.external_reference_required("real-1") is True


def test_reconciliation_requires_matching_durable_external_reference(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("real-reconcile")
    with pytest.raises(ValueError, match="external_id"):
        ledger.reconcile("real-reconcile", executed=True, external_id="not-durable")
    assert ledger.status("real-reconcile") is ExecutionLedgerStatus.RESERVED

    ledger.attach_external_id("real-reconcile", "broker-reconcile")
    ledger.reconcile("real-reconcile", executed=True, external_id="broker-reconcile")
    assert ledger.status("real-reconcile") is ExecutionLedgerStatus.RECONCILED_EXECUTED


def test_real_ledger_persists_broker_identity(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("real-broker", broker_id="broker-a")
    restored = ExecutionLedger(path)
    assert restored.broker_id("real-broker") == "broker-a"


def test_legacy_ledger_without_broker_remains_readable(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"legacy": "ACCEPTED"}', encoding="utf-8")
    assert ExecutionLedger(path).broker_id("legacy") is None
