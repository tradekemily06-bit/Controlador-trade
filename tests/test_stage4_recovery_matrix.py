from __future__ import annotations

import json
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def _coordinator(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    return RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
    ), ledger, lifecycle, checkpoint


def test_corrupt_checkpoint_fails_closed_without_resume(tmp_path):
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text("{not-json", encoding="utf-8")
    coordinator, _, _, _ = _coordinator(tmp_path)

    assessment = coordinator.assess()

    assert assessment.state is RecoveryState.INVALID
    assert not assessment.can_resume


def test_unknown_lifecycle_survives_restart_and_requires_reconciliation(tmp_path):
    coordinator, _, lifecycle, checkpoint = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    lifecycle.put(ExecutionLifecycleRecord("req-unknown", ExecutionLifecycleState.UNKNOWN, now, "ambiguous"))
    checkpoint.save(RuntimeCheckpoint("session-a", 7, "req-unknown", now))

    restarted, _, restarted_lifecycle, _ = _coordinator(tmp_path)
    assessment = restarted.assess(session_id="session-a")

    assert restarted_lifecycle.get("req-unknown").state is ExecutionLifecycleState.UNKNOWN
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.unknown_request_ids == ("req-unknown",)
    assert not assessment.can_resume


def test_reserved_ledger_blocks_resume_even_if_lifecycle_is_missing(tmp_path):
    coordinator, ledger, _, _ = _coordinator(tmp_path)
    ledger.reserve("req-reserved")

    assessment = coordinator.assess()

    assert ledger.status("req-reserved") is ExecutionLedgerStatus.RESERVED
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert "req-reserved" in assessment.unknown_request_ids
    assert not assessment.can_resume


def test_checkpoint_session_mismatch_blocks_clean_resume(tmp_path):
    coordinator, _, _, checkpoint = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    checkpoint.save(RuntimeCheckpoint("session-a", 1, None, now))

    assessment = coordinator.assess(session_id="session-b")

    assert assessment.state is RecoveryState.SESSION_MISMATCH
    assert not assessment.can_resume


def test_corrupt_lifecycle_fails_closed(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle_path.write_text(json.dumps({"unexpected": True}), encoding="utf-8")

    with pytest.raises(ValueError):
        ExecutionLifecycleStore(lifecycle_path)


def test_unknown_lifecycle_cannot_be_overwritten_by_normal_transition(tmp_path):
    _, _, lifecycle, _ = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    lifecycle.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now))

    with pytest.raises(ValueError):
        lifecycle.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))


def test_clean_checkpoint_without_pending_state_can_resume(tmp_path):
    coordinator, _, _, checkpoint = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    checkpoint.save(RuntimeCheckpoint("session-a", 4, None, now))

    assessment = coordinator.assess(session_id="session-a")

    assert assessment.state is RecoveryState.SAFE_TO_RESUME
    assert assessment.can_resume


def _reserve_worker(ledger_path: str, start_event, result_queue) -> None:
    start_event.wait(timeout=10)
    ledger = ExecutionLedger(Path(ledger_path))
    try:
        ledger.reserve("shared-request")
    except ValueError:
        result_queue.put("rejected")
    else:
        result_queue.put("reserved")


def test_cross_process_reservation_has_single_winner(tmp_path):
    ledger_path = tmp_path / "shared-ledger.json"
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_reserve_worker,
            args=(str(ledger_path), start_event, result_queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()

    start_event.set()
    results = sorted(result_queue.get(timeout=10) for _ in processes)
    for process in processes:
        process.join(timeout=10)

    assert results == ["rejected", "reserved"]
    assert ExecutionLedger(ledger_path).status("shared-request") is ExecutionLedgerStatus.RESERVED
    assert all(process.exitcode == 0 for process in processes)
