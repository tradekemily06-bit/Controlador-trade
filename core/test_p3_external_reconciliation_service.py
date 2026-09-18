from pathlib import Path

import pytest

from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.p3_execution_reconciliation import ExecutionReconciliationCoordinator
from core.p3_external_reconciliation_service import ExternalExecutionReconciliationService
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def test_service_queries_exact_durable_external_id_and_reconciles(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("req-query")
    ledger.bind_external_id("req-query", "EXT-QUERY")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "req-query",
            ExecutionLifecycleState.UNKNOWN,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "timeout",
        )
    )

    class Query:
        def __init__(self):
            self.seen = []

        def query_order(self, external_id):
            self.seen.append(external_id)
            return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "filled")

    query = Query()
    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle),
        query_port=query,
    )

    result = service.reconcile_request("req-query")

    assert query.seen == ["EXT-QUERY"]
    assert result.status is ExternalOrderStatus.EXECUTED
    assert ledger.status("req-query") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("req-query").state is ExecutionLifecycleState.ACCEPTED


def test_service_rejects_missing_durable_external_id_without_query(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("req-no-id")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "req-no-id",
            ExecutionLifecycleState.UNKNOWN,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
    )

    class Query:
        def query_order(self, _external_id):
            raise AssertionError("broker query must not happen without durable external_id")

    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle),
        query_port=Query(),
    )

    with pytest.raises(ValueError, match="external_id durável"):
        service.reconcile_request("req-no-id")


def test_service_rejects_mismatched_external_identity(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("req-mismatch")
    ledger.bind_external_id("req-mismatch", "EXT-REAL")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "req-mismatch",
            ExecutionLifecycleState.UNKNOWN,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
    )

    class Query:
        def query_order(self, _external_id):
            return ExternalOrderObservation("EXT-OTHER", ExternalOrderStatus.EXECUTED, "wrong identity")

    service = ExternalExecutionReconciliationService(
        coordinator=ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle),
        query_port=Query(),
    )

    with pytest.raises(ValueError, match="diferente da identidade durável"):
        service.reconcile_request("req-mismatch")

    assert ledger.status("req-mismatch") is ExecutionLedgerStatus.RESERVED
    assert lifecycle.get("req-mismatch").state is ExecutionLifecycleState.UNKNOWN
