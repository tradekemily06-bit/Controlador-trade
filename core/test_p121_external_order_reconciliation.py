from datetime import datetime, timezone
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
import pytest

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


def test_terminal_external_status_reconciles():
    boundary = ExternalOrderReconciliationBoundary()
    result = boundary.reconcile(
        "ext-1",
        ExternalOrderObservation("ext-1", ExternalOrderStatus.EXECUTED, "filled"),
    )
    assert result.reconciled is True
    assert result.status is ExternalOrderStatus.EXECUTED


def test_not_executed_is_terminal():
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-2",
        ExternalOrderObservation("ext-2", ExternalOrderStatus.NOT_EXECUTED, "cancelled"),
    )
    assert result.reconciled is True


@pytest.mark.parametrize("status", [ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN])
def test_ambiguous_external_status_does_not_close_reconciliation(status):
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-3", ExternalOrderObservation("ext-3", status, "not final"),
    )
    assert result.reconciled is False


def test_external_id_mismatch_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(
            "ext-4",
            ExternalOrderObservation("other", ExternalOrderStatus.EXECUTED, "filled"),
        )


def test_invalid_external_id_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(
            " ",
            ExternalOrderObservation("ext", ExternalOrderStatus.UNKNOWN, "unknown"),
        )


def test_reconcile_request_uses_durable_external_id_and_projects_terminal_state(tmp_path):
    class Query:
        def query_order(self, external_id):
            assert external_id == "broker-42"
            return ExternalOrderObservation("broker-42", ExternalOrderStatus.EXECUTED, "broker confirmed")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("req-42")
    ledger.attach_external_id("req-42", "broker-42")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "req-42",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )
    ledger.mark_unknown("req-42")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "req-42",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
        )
    )

    result = ExternalOrderReconciliationBoundary().reconcile_request(
        request_id="req-42",
        ledger=ledger,
        lifecycle=lifecycle,
        query_port=Query(),
    )

    assert result.reconciled is True
    assert ledger.status("req-42") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("req-42").state is ExecutionLifecycleState.ACCEPTED


def test_reconcile_request_requires_durable_external_id(tmp_path):
    class Query:
        def query_order(self, external_id):
            raise AssertionError("query must not run")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("req-no-id")

    with pytest.raises(ValueError, match="external_id durável"):
        ExternalOrderReconciliationBoundary().reconcile_request(
            request_id="req-no-id",
            ledger=ledger,
            lifecycle=lifecycle,
            query_port=Query(),
        )
