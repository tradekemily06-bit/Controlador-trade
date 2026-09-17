from __future__ import annotations

import os
import stat
from datetime import datetime, timezone

import pytest

from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


@pytest.mark.parametrize("kind", ("checkpoint", "lifecycle", "ledger"))
def test_authoritative_json_replace_fsyncs_containing_directory(tmp_path, monkeypatch, kind):
    fsynced_directories: list[int] = []
    original_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            fsynced_directories.append(fd)
        original_fsync(fd)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    now = datetime.now(timezone.utc)

    if kind == "checkpoint":
        RuntimeCheckpointStore(tmp_path / "checkpoint.json").save(RuntimeCheckpoint("session-a", 1, None, now))
    elif kind == "lifecycle":
        ExecutionLifecycleStore(tmp_path / "lifecycle.json").put(
            ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now)
        )
    else:
        ExecutionLedger(tmp_path / "ledger.json").reserve("req-1")

    assert fsynced_directories, f"{kind} must fsync its containing directory after os.replace"
