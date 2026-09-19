from pathlib import Path

import pytest

from core.durable_json import MAX_JSON_BYTES, atomic_write_json, read_json


def test_read_json_rejects_oversized_payload(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_bytes(b"x" * (MAX_JSON_BYTES + 1))

    with pytest.raises(ValueError, match="grande demais"):
        read_json(path, {})


def test_atomic_write_json_rejects_oversized_payload_without_commit(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text('{"safe": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="grande demais"):
        atomic_write_json(path, {"payload": "x" * MAX_JSON_BYTES})

    assert path.read_text(encoding="utf-8") == '{"safe": true}'
