from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.durable_json import read_json
from core.runtime_checkpoint import RuntimeCheckpointStore


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW não disponível")
def test_read_json_rejects_final_component_symlink(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"safe": true}', encoding="utf-8")
    link = tmp_path / "alias.json"
    link.symlink_to(target)

    with pytest.raises(OSError):
        read_json(link, {})


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW não disponível")
def test_checkpoint_load_fails_closed_on_final_component_symlink(tmp_path: Path) -> None:
    real = tmp_path / "checkpoint.json"
    real.write_text(
        '{"session_id":"s1","last_cycle":1,"last_request_id":null,'
        '"updated_at":"2026-09-19T00:00:00+00:00"}',
        encoding="utf-8",
    )
    link = tmp_path / "runtime.json"
    link.symlink_to(real)

    with pytest.raises(ValueError):
        RuntimeCheckpointStore(link).load()
