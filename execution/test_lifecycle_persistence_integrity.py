from pathlib import Path

import pytest

from execution.execution_lifecycle import ExecutionLifecycleStore


def test_duplicate_request_id_in_persisted_lifecycle_fails_closed(tmp_path: Path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        "["
        '{"request_id":"req-1","state":"PENDING","updated_at":"2026-01-01T00:00:00+00:00"},'
        '{"request_id":"req-1","state":"UNKNOWN","updated_at":"2026-01-01T00:00:01+00:00"}'
        "]",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)
