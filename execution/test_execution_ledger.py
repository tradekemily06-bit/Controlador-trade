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


def test_unknown_cannot_jump_to_terminal_without_reconciliation(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-unknown")
    ledger.mark_unknown("req-unknown")
    with pytest.raises(ValueError, match="UNKNOWN exige reconciliação explícita"):
        ledger.mark_accepted("req-unknown")
    with pytest.raises(ValueError, match="UNKNOWN exige reconciliação explícita"):
        ledger.mark_rejected("req-unknown")


def test_terminal_ledger_state_is_immutable(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-terminal")
    ledger.mark_accepted("req-terminal")
    with pytest.raises(ValueError, match="transição terminal inválida"):
        ledger.mark_rejected("req-terminal")


def test_executed_reconciliation_cannot_mint_external_identity(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-reconcile")
    ledger.mark_unknown("req-reconcile")

    with pytest.raises(ValueError, match="não pode criar external_id"):
        ledger.reconcile("req-reconcile", executed=True, external_id="broker-123")

    assert ledger.status("req-reconcile").value == "UNKNOWN"
    assert ledger.external_id("req-reconcile") is None


def test_executed_reconciliation_requires_the_durable_external_identity(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-reconcile-durable")
    ledger.bind_external_id("req-reconcile-durable", "broker-123")
    ledger.mark_unknown("req-reconcile-durable")

    ledger.reconcile("req-reconcile-durable", executed=True, external_id="broker-123")

    assert ledger.status("req-reconcile-durable").value == "RECONCILED_EXECUTED"


def test_external_id_cannot_be_bound_to_terminal_nonexecuted_state(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-rejected")
    ledger.mark_rejected("req-rejected")
    try:
        ledger.bind_external_id("req-rejected", "ext-rejected")
    except ValueError:
        pass
    else:
        raise AssertionError("rejected requests must not acquire an external execution identity")
    ledger.reserve("req-unknown")
    ledger.mark_unknown("req-unknown")
    ledger.bind_external_id("req-unknown", "ext-unknown")
    assert ledger.external_id("req-unknown") == "ext-unknown"


def test_ledger_persistence_flushes_before_atomic_replace(tmp_path, monkeypatch):
    import os
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    calls = []
    real_fsync = os.fsync
    real_replace = os.replace

    def fsync(fd):
        calls.append("fsync")
        return real_fsync(fd)

    def replace(src, dst):
        calls.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    ledger.record("req-durable")
    assert calls.index("fsync") < calls.index("replace")
    assert calls.count("fsync") >= (1 if os.name == "nt" else 2)


def test_ledger_rejects_impossible_external_id_state(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"bad": {"state": "REJECTED", "external_id": "broker-1"}}), encoding="utf-8")
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
