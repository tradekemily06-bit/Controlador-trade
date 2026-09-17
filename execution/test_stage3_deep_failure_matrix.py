from pathlib import Path

import pytest

from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus


def test_reserved_state_survives_restart_and_blocks_replay(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    first.reserve("req-reserved")

    restored = ExecutionLedger(path)

    assert restored.status("req-reserved") is ExecutionLedgerStatus.RESERVED
    with pytest.raises(ValueError, match="replay REAL recusado"):
        restored.reserve("req-reserved")


def test_unknown_state_survives_restart_and_requires_explicit_reconciliation(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    first.reserve("req-unknown")
    first.mark_unknown("req-unknown")

    restored = ExecutionLedger(path)

    assert restored.status("req-unknown") is ExecutionLedgerStatus.UNKNOWN
    with pytest.raises(ValueError, match="replay REAL recusado"):
        restored.reserve("req-unknown")


def test_reconciliation_requires_authoritative_evidence(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-evidence")
    ledger.mark_unknown("req-evidence")

    with pytest.raises(ValueError, match="evidence_id e evidence_source autoritativos"):
        ledger.reconcile("req-evidence", executed=True)


def test_reconciliation_requires_complete_evidence_pair(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-evidence")
    ledger.mark_unknown("req-evidence")

    with pytest.raises(ValueError, match="evidence_id e evidence_source autoritativos"):
        ledger.reconcile("req-evidence", executed=True, evidence_id="evidence-1")

    with pytest.raises(ValueError, match="evidence_id e evidence_source autoritativos"):
        ledger.reconcile("req-evidence", executed=True, evidence_source="broker")


def test_reconciliation_evidence_id_cannot_be_reused(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-one")
    ledger.mark_unknown("req-one")
    ledger.reserve("req-two")
    ledger.mark_unknown("req-two")

    ledger.reconcile(
        "req-one",
        executed=True,
        evidence_id="broker-event-1",
        evidence_source="demo-broker",
    )

    with pytest.raises(ValueError, match="evidence_id já está vinculado"):
        ledger.reconcile(
            "req-two",
            executed=False,
            evidence_id="broker-event-1",
            evidence_source="demo-broker",
        )


def test_reconciled_terminal_state_survives_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-reconciled")
    ledger.mark_unknown("req-reconciled")
    ledger.reconcile(
        "req-reconciled",
        executed=False,
        evidence_id="broker-event-2",
        evidence_source="demo-broker",
    )

    restored = ExecutionLedger(path)

    assert restored.status("req-reconciled") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
    assert restored.reconciliation_evidence("req-reconciled") == {
        "evidence_id": "broker-event-2",
        "evidence_source": "demo-broker",
    }
