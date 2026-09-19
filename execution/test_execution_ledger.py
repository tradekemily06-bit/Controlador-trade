from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
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
    with pytest.raises(ValueError, match="request_id inválido"):
        ledger.contains(" ")


def test_ledger_persists_external_id_for_accepted_execution(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-1")
    ledger.mark_accepted("req-1", "BROKER-123")
    reloaded = ExecutionLedger(path)
    assert reloaded.status("req-1") is ExecutionLedgerStatus.ACCEPTED
    assert reloaded.external_id("req-1") == "BROKER-123"


def test_ledger_loads_legacy_status_only_format(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{"req-1": "ACCEPTED"}', encoding="utf-8")
    ledger = ExecutionLedger(path)
    assert ledger.status("req-1") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("req-1") is None


def test_ledger_rejects_external_id_reuse(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1")
    ledger.mark_accepted("req-1", "BROKER-123")
    ledger.reserve("req-2")
    with pytest.raises(ValueError):
        ledger.mark_accepted("req-2", "BROKER-123")

def test_ledger_rejects_acceptance_without_external_id(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-no-external")
    with pytest.raises(ValueError, match="external_id obrigatório"):
        ledger.mark_accepted("req-no-external", None)


def test_ledger_reconciles_only_from_request_bound_terminal_observation(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-reconcile")
    ledger.mark_unknown("req-reconcile")
    ledger.reconcile_observation(
        "req-reconcile",
        ExternalOrderObservation("BROKER-9", ExternalOrderStatus.EXECUTED, "filled", request_id="req-reconcile"),
    )
    restored = ExecutionLedger(path)
    assert restored.status("req-reconcile") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert restored.external_id("req-reconcile") == "BROKER-9"


def test_ledger_reconciliation_rejects_external_id_mismatch(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-mismatch")
    ledger.mark_accepted("req-mismatch", "BROKER-10")
    with pytest.raises(ValueError):
        ledger.reconcile_observation(
            "req-mismatch",
            ExternalOrderObservation("BROKER-11", ExternalOrderStatus.EXECUTED, "wrong", request_id="req-mismatch"),
        )


def test_ledger_reconciliation_rejects_nonterminal_observation(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-pending")
    ledger.mark_unknown("req-pending")
    with pytest.raises(ValueError, match="não é terminal"):
        ledger.reconcile_observation(
            "req-pending",
            ExternalOrderObservation(None, ExternalOrderStatus.PENDING, "still pending", request_id="req-pending"),
        )
