from __future__ import annotations

from datetime import datetime, timedelta, timezone
from multiprocessing import Process
from pathlib import Path

from core.ecosystem_maintenance import MaintenanceManager
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def _put_lifecycle(path: str, request_id: str) -> None:
    store = ExecutionLifecycleStore(path)
    store.put(
        ExecutionLifecycleRecord(
            request_id=request_id,
            state=ExecutionLifecycleState.PENDING,
            updated_at=datetime.now(timezone.utc),
        )
    )


def _save_checkpoint(path: str, session_id: str, cycle: int) -> None:
    RuntimeCheckpointStore(path).save(
        RuntimeCheckpoint(
            session_id=session_id,
            last_cycle=cycle,
            last_request_id=f"req-{cycle}",
            updated_at=datetime.now(timezone.utc),
        )
    )


def _schedule_maintenance(path: str, maintenance_id: str, start: datetime, result_path: str) -> None:
    try:
        MaintenanceManager(path).schedule(
            maintenance_id=maintenance_id,
            title="Concurrent test",
            message="test",
            starts_at=start,
            duration_minutes=10,
            now=start - timedelta(minutes=1),
        )
        Path(result_path).write_text("ok", encoding="utf-8")
    except Exception as exc:  # pragma: no cover - child process reports outcome
        Path(result_path).write_text(type(exc).__name__, encoding="utf-8")


def _join(*processes: Process) -> None:
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0


def test_lifecycle_concurrent_writers_do_not_lose_records(tmp_path):
    path = str(tmp_path / "lifecycle.json")
    processes = [
        Process(target=_put_lifecycle, args=(path, f"req-{index}"))
        for index in range(8)
    ]
    _join(*processes)

    records = ExecutionLifecycleStore(path).records()
    assert {record.request_id for record in records} == {f"req-{index}" for index in range(8)}


def test_checkpoint_concurrent_writers_always_leave_valid_state(tmp_path):
    path = str(tmp_path / "checkpoint.json")
    processes = [
        Process(target=_save_checkpoint, args=(path, f"session-{index}", index))
        for index in range(8)
    ]
    _join(*processes)

    checkpoint = RuntimeCheckpointStore(path).load()
    assert checkpoint is not None
    assert checkpoint.session_id.startswith("session-")
    assert checkpoint.last_request_id == f"req-{checkpoint.last_cycle}"


def test_maintenance_concurrent_schedule_allows_only_one_window(tmp_path):
    path = str(tmp_path / "maintenance.json")
    start = datetime.now(timezone.utc) + timedelta(minutes=5)
    result_paths = [str(tmp_path / f"result-{index}.txt") for index in range(2)]
    processes = [
        Process(target=_schedule_maintenance, args=(path, f"maintenance-{index}", start, result_paths[index]))
        for index in range(2)
    ]
    _join(*processes)

    outcomes = [Path(result).read_text(encoding="utf-8") for result in result_paths]
    assert outcomes.count("ok") == 1
    assert outcomes.count("ValueError") == 1
    status = MaintenanceManager(path).status(now=start - timedelta(minutes=1))
    assert status["status"] == "SCHEDULED"
    assert status["maintenance"]["maintenance_id"] in {"maintenance-0", "maintenance-1"}
