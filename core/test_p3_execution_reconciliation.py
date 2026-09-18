from threading import Barrier, Thread
from datetime import datetime, timezone

import pytest

from core.p3_execution_reconciliation import ExecutionReconciliationCoordinator
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.operation_memory import OperationMemory
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def build(tmp_path):
    return (
        ExecutionLedger(tmp_path / "ledger.json"),
        ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
    )


def test_unknown_executed_reconciliation_closes_both_authorities(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-unknown"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.mark_unknown(request_id)
    ledger.bind_external_id(request_id, "ext-1")
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now, "timeout"))

    result = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
        request_id,
        "ext-1",
        ExternalOrderObservation("ext-1", ExternalOrderStatus.EXECUTED, "filled"),
        updated_at=now,
    )

    assert result.reconciled is True
    assert ledger.status(request_id) is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.ACCEPTED


def test_reserved_not_executed_reconciliation_is_safe_and_closes_both(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-reserved"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-2")
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, now, "before broker"))

    ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
        request_id,
        "ext-2",
        ExternalOrderObservation("ext-2", ExternalOrderStatus.NOT_EXECUTED, "cancelled"),
        updated_at=now,
    )

    assert ledger.status(request_id) is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.REJECTED


def test_orphan_terminal_ledger_can_be_completed_only_with_matching_external_fact(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-orphan"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-3")
    ledger.mark_accepted(request_id)

    ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
        request_id,
        "ext-3",
        ExternalOrderObservation("ext-3", ExternalOrderStatus.EXECUTED, "confirmed"),
        updated_at=now,
    )

    assert lifecycle.get(request_id).state is ExecutionLifecycleState.ACCEPTED


def test_orphan_terminal_ledger_mismatch_is_rejected_without_mutation(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-mismatch"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.mark_accepted(request_id)

    with pytest.raises(ValueError, match="compatível"):
        ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
            request_id,
            "ext-4",
            ExternalOrderObservation("ext-4", ExternalOrderStatus.NOT_EXECUTED, "not found"),
            updated_at=now,
        )

    assert ledger.status(request_id) is ExecutionLedgerStatus.ACCEPTED
    assert lifecycle.get(request_id) is None


def test_orphan_lifecycle_never_creates_retroactive_real_ledger(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-lifecycle-only"
    now = datetime.now(timezone.utc)
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now, "uncertain"))

    with pytest.raises(ValueError, match="ledger ausente"):
        ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
            request_id,
            "ext-5",
            ExternalOrderObservation("ext-5", ExternalOrderStatus.EXECUTED, "filled"),
            updated_at=now,
        )

    assert ledger.status(request_id) is None
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.UNKNOWN


def test_pending_external_status_does_not_change_anything(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-pending"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, now))

    result = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
        request_id,
        "ext-6",
        ExternalOrderObservation("ext-6", ExternalOrderStatus.PENDING, "still open"),
        updated_at=now,
    )

    assert result.reconciled is False
    assert ledger.status(request_id) is ExecutionLedgerStatus.RESERVED
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.PENDING


def test_repeated_reconciliation_is_idempotent(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-retry"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-7")
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now))

    coordinator = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle)
    observation = ExternalOrderObservation("ext-7", ExternalOrderStatus.EXECUTED, "filled")
    coordinator.reconcile(request_id, "ext-7", observation, updated_at=now)

    # A second identical reconciliation must not reopen or alter a terminal state.
    coordinator.reconcile(request_id, "ext-7", observation, updated_at=now)

    assert ledger.status(request_id) is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.ACCEPTED


def test_reconciliation_keeps_recovery_blocked_if_cross_store_write_fails(tmp_path, monkeypatch):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-partial"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-8")
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now))

    original = lifecycle.reconcile
    calls = {"count": 0}

    def fail_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated lifecycle outage")
        return original(*args, **kwargs)

    monkeypatch.setattr(lifecycle, "reconcile", fail_once)

    with pytest.raises(OSError, match="simulated lifecycle outage"):
        ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
            request_id,
            "ext-8",
            ExternalOrderObservation("ext-8", ExternalOrderStatus.EXECUTED, "filled"),
            updated_at=now,
        )

    # Ledger may already be terminal, but lifecycle remains UNKNOWN; recovery
    # must continue to block until the retry completes.
    assert ledger.status(request_id) is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.UNKNOWN

    coordinator = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle)
    coordinator.reconcile(
        request_id,
        "ext-8",
        ExternalOrderObservation("ext-8", ExternalOrderStatus.EXECUTED, "filled"),
        updated_at=now,
    )

    assert lifecycle.get(request_id).state is ExecutionLifecycleState.ACCEPTED


def test_uncertain_reconciliation_rejects_external_id_mismatch_without_mutation(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-bound-mismatch"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-bound")
    ledger.mark_unknown(request_id)
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now, "timeout"))

    coordinator = ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle)
    with pytest.raises(ValueError, match="identidade externa"):
        coordinator.reconcile(
            request_id,
            "ext-other",
            ExternalOrderObservation("ext-other", ExternalOrderStatus.EXECUTED, "filled"),
            updated_at=now,
        )

    assert ledger.status(request_id) is ExecutionLedgerStatus.UNKNOWN
    assert ledger.external_id(request_id) == "ext-bound"
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.UNKNOWN


def test_uncertain_reconciliation_without_durable_external_id_fails_closed(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-no-bound-id"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.mark_unknown(request_id)
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now, "timeout"))

    with pytest.raises(ValueError, match="sem external_id"):
        ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
            request_id,
            "ext-unproven",
            ExternalOrderObservation("ext-unproven", ExternalOrderStatus.EXECUTED, "filled"),
            updated_at=now,
        )

    assert ledger.status(request_id) is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get(request_id).state is ExecutionLifecycleState.UNKNOWN


def test_terminal_ledger_with_bound_external_id_rejects_foreign_external_fact(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-terminal-bound"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-terminal")
    ledger.mark_accepted(request_id)

    with pytest.raises(ValueError, match="identidade externa"):
        ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
            request_id,
            "ext-foreign",
            ExternalOrderObservation("ext-foreign", ExternalOrderStatus.EXECUTED, "filled"),
            updated_at=now,
        )

    assert ledger.status(request_id) is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id(request_id) == "ext-terminal"
    assert lifecycle.get(request_id) is None


def test_terminal_ledger_without_external_id_cannot_consume_foreign_external_fact(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-legacy-terminal"
    now = datetime.now(timezone.utc)
    ledger.record(request_id)

    with pytest.raises(ValueError, match="external_id durável"):
        ExecutionReconciliationCoordinator(ledger=ledger, lifecycle=lifecycle).reconcile(
            request_id,
            "ext-unproven-terminal",
            ExternalOrderObservation("ext-unproven-terminal", ExternalOrderStatus.EXECUTED, "filled"),
            updated_at=now,
        )

    assert ledger.status(request_id) is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id(request_id) is None
    assert lifecycle.get(request_id) is None


def test_concurrent_identical_reconciliation_is_idempotent(tmp_path):
    ledger, lifecycle = build(tmp_path)
    request_id = "req-concurrent-reconcile"
    now = datetime.now(timezone.utc)
    ledger.reserve(request_id)
    ledger.bind_external_id(request_id, "ext-concurrent")
    lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, now, "timeout"))

    observation = ExternalOrderObservation(
        "ext-concurrent",
        ExternalOrderStatus.EXECUTED,
        "filled",
    )
    coordinators = [
        ExecutionReconciliationCoordinator(
            ledger=ExecutionLedger(ledger.path),
            lifecycle=ExecutionLifecycleStore(lifecycle.path),
        )
        for _ in range(2)
    ]
    barrier = Barrier(2)
    errors = []

    def run(coordinator):
        try:
            barrier.wait()
            coordinator.reconcile(
                request_id,
                "ext-concurrent",
                observation,
                updated_at=now,
            )
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=run, args=(coordinator,)) for coordinator in coordinators]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert ExecutionLedger(ledger.path).status(request_id) is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLedger(ledger.path).external_id(request_id) == "ext-concurrent"
    assert ExecutionLifecycleStore(lifecycle.path).get(request_id).state is ExecutionLifecycleState.ACCEPTED
