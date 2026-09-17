from datetime import datetime, timezone

import pytest

from execution.execution_lifecycle import ExecutionLifecycleStore


def test_duplicate_persisted_request_id_fails_closed(tmp_path):
    path = tmp_path / "lifecycle.json"
    timestamp = datetime.now(timezone.utc).isoformat()
    path.write_text(
        "["
        f'{{"request_id":"req-1","state":"PENDING","updated_at":"{timestamp}","message":"first"}},'
        f'{{"request_id":"req-1","state":"ACCEPTED","updated_at":"{timestamp}","message":"second"}}'
        "]",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)
