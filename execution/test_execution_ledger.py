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


def test_real_ledger_persists_external_identity_and_reconciliation_evidence(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("req-real", broker_id="fake", symbol="EURUSD")
    assert ledger.execution_context("req-real") == {
        "broker_id": "fake",
        "symbol": "EURUSD",
        "external_id": None,
    }
    ledger.mark_accepted_real("req-real", external_id="ext-1")
    assert ledger.execution_context("req-real")["external_id"] == "ext-1"
    ledger2 = ExecutionLedger(path)
    assert ledger2.status("req-real") is ExecutionLedgerStatus.ACCEPTED
    assert ledger2.execution_context("req-real")["external_id"] == "ext-1"


def test_reconciliation_requires_unique_explicit_evidence(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("req-real", broker_id="fake", symbol="EURUSD")
    ledger.mark_unknown("req-real")
    ledger.reconcile("req-real", executed=True, evidence_id="event-1", evidence_source="fake-broker")
    assert ledger.reconciliation_evidence("req-real") == {
        "evidence_id": "event-1",
        "evidence_source": "fake-broker",
    }


def test_reconciliation_rejects_reused_evidence(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("req-1", broker_id="fake", symbol="EURUSD")
    ledger.mark_unknown("req-1")
    ledger.reconcile("req-1", executed=True, evidence_id="event-1", evidence_source="fake-broker")
    ledger.reserve_real("req-2", broker_id="fake", symbol="EURUSD")
    ledger.mark_unknown("req-2")
    with pytest.raises(ValueError):
        ledger.reconcile("req-2", executed=False, evidence_id="event-1", evidence_source="fake-broker")
