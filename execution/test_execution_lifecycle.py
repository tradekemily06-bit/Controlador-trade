from datetime import datetime, timezone

import pytest

from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def test_lifecycle_survives_restart(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now, "started"))
    assert ExecutionLifecycleStore(path).get("req-1").state is ExecutionLifecycleState.PENDING


def test_unknown_blocks_implicit_transition(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))
    with pytest.raises(ValueError, match="UNKNOWN"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted"))


def test_unknown_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now))
    result = store.reconcile("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="confirmed")
    assert result.state is ExecutionLifecycleState.ACCEPTED
    assert ExecutionLifecycleStore(path).get("req-1") == result


def test_invalid_persisted_state_fails_closed(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text('[{"request_id":"req-1","state":"INVALID","updated_at":"bad"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)


def test_reconciliation_requires_existing_request(tmp_path):
    with pytest.raises(ValueError, match="não encontrada"):
        ExecutionLifecycleStore(tmp_path / "lifecycle.json").reconcile(
            "missing", ExecutionLifecycleState.REJECTED, updated_at=datetime.now(timezone.utc)
        )


def test_lifecycle_rejects_duplicate_request_ids_in_persisted_list(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        """[
          {"request_id": "dup", "state": "PENDING", "updated_at": "2026-09-18T12:00:00+00:00"},
          {"request_id": "dup", "state": "PENDING", "updated_at": "2026-09-18T12:01:00+00:00"}
        ]""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)


def test_lifecycle_publication_failure_preserves_previous_durable_state(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle.json"
    store = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("stable", ExecutionLifecycleState.PENDING, now))

    def fail_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("execution.execution_lifecycle.os.fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated fsync failure"):
        store.put(ExecutionLifecycleRecord("stable", ExecutionLifecycleState.UNKNOWN, now))

    assert ExecutionLifecycleStore(path).get("stable").state is ExecutionLifecycleState.PENDING
    assert not path.with_name(".lifecycle.json.tmp").exists()




def test_lifecycle_rejects_noncanonical_request_id_and_nonfinite_json(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    with pytest.raises(ValueError, match="canônico"):
        store.put(ExecutionLifecycleRecord(" req-1 ", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)))
    store.path.write_text('[{"request_id":"req-1","state":"PENDING","updated_at":NaN}]', encoding="utf-8")
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        store.records()
