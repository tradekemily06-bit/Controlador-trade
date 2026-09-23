from datetime import datetime, timezone

from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus


def test_ledger_two_instances_preserve_reservations(tmp_path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    second = ExecutionLedger(path)
    first.reserve("req-1")
    second.reserve("req-2")
    reloaded = ExecutionLedger(path)
    assert reloaded.status("req-1") is ExecutionLedgerStatus.RESERVED
    assert reloaded.status("req-2") is ExecutionLedgerStatus.RESERVED


def test_ledger_unknown_requires_explicit_reconciliation(tmp_path):
    store = ExecutionLedger(tmp_path / "ledger.json")
    store.reserve("req-1")
    store.mark_unknown("req-1")
    try:
        store.mark_accepted("req-1")
    except ValueError as exc:
        assert "transição inválida" in str(exc)
    else:
        raise AssertionError("UNKNOWN must not be accepted without reconciliation")

    store.reconcile("req-1", executed=True)
    assert store.status("req-1") is ExecutionLedgerStatus.RECONCILED_EXECUTED
