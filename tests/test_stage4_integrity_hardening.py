from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def test_ledger_reconciliation_requires_authoritative_evidence_pair(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-1")
    ledger.mark_unknown("req-1")

    with pytest.raises(ValueError):
        ledger.reconcile("req-1", executed=False)
    with pytest.raises(ValueError):
        ledger.reconcile("req-1", executed=False, evidence_id="e-1")
    with pytest.raises(ValueError):
        ledger.reconcile("req-1", executed=False, evidence_source="broker")

    ledger.reconcile("req-1", executed=False, evidence_id="e-1", evidence_source="broker-reconciliation")
    assert ledger.status("req-1") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
    assert ledger.reconciliation_evidence("req-1") == {
        "evidence_id": "e-1",
        "evidence_source": "broker-reconciliation",
    }


def test_ledger_reconciliation_evidence_id_cannot_be_reused(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    for request_id in ("req-1", "req-2"):
        ledger.reserve(request_id)
        ledger.mark_unknown(request_id)
    ledger.reconcile("req-1", executed=False, evidence_id="same", evidence_source="broker")

    with pytest.raises(ValueError):
        ledger.reconcile("req-2", executed=False, evidence_id="same", evidence_source="broker")


def test_lifecycle_duplicate_request_id_on_disk_fails_closed(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps([
        {"request_id": "dup", "state": "PENDING", "updated_at": now, "message": "a"},
        {"request_id": "dup", "state": "UNKNOWN", "updated_at": now, "message": "b"},
    ]), encoding="utf-8")

    with pytest.raises(ValueError):
        ExecutionLifecycleStore(path)


def test_unknown_lifecycle_requires_explicit_reconciliation(tmp_path):
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    lifecycle.put(ExecutionLifecycleRecord("req-unknown", ExecutionLifecycleState.UNKNOWN, now))

    with pytest.raises(ValueError):
        lifecycle.put(ExecutionLifecycleRecord("req-unknown", ExecutionLifecycleState.ACCEPTED, now))

    reconciled = lifecycle.reconcile("req-unknown", ExecutionLifecycleState.REJECTED, updated_at=now, message="verified")
    assert reconciled.state is ExecutionLifecycleState.REJECTED
