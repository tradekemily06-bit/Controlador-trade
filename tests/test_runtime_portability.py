from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import runtime_portability as portability


def test_restore_replace_false_refuses_to_overwrite_state(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text('{"from":"backup"}', encoding="utf-8")
    backup = tmp_path / "runtime.zip"
    portability.create_backup(source, backup)

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    target = runtime / "operation-memory.json"
    target.write_text('{"keep":"current"}', encoding="utf-8")

    with pytest.raises(FileExistsError):
        portability.restore_backup(backup, runtime)

    assert target.read_text(encoding="utf-8") == '{"keep":"current"}'


def test_restore_rolls_back_committed_files_if_a_later_replace_fails(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text('{"from":"backup"}', encoding="utf-8")
    (source / "operational-safety.json").write_text('{"from":"backup"}', encoding="utf-8")
    backup = tmp_path / "runtime.zip"
    portability.create_backup(source, backup)

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    first = runtime / "operation-memory.json"
    second = runtime / "operational-safety.json"
    first.write_text('{"keep":"first"}', encoding="utf-8")
    second.write_text('{"keep":"second"}', encoding="utf-8")

    real_replace = os.replace
    failed = False

    def fail_once_on_second_incoming(src, dst):
        nonlocal failed
        src_path = Path(src)
        dst_path = Path(dst)
        if (
            not failed
            and src_path.parent.name == "incoming"
            and dst_path.name == "operational-safety.json"
        ):
            failed = True
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(portability.os, "replace", fail_once_on_second_incoming)

    with pytest.raises(OSError, match="simulated replace failure"):
        portability.restore_backup(backup, runtime, replace=True)

    assert first.read_text(encoding="utf-8") == '{"keep":"first"}'
    assert second.read_text(encoding="utf-8") == '{"keep":"second"}'


def test_restore_replaces_all_files_after_successful_staging(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text('{"from":"backup"}', encoding="utf-8")
    (source / "operational-safety.json").write_text('{"from":"backup"}', encoding="utf-8")
    backup = tmp_path / "runtime.zip"
    portability.create_backup(source, backup)

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "operation-memory.json").write_text('{"old":1}', encoding="utf-8")
    (runtime / "operational-safety.json").write_text('{"old":2}', encoding="utf-8")

    result = portability.restore_backup(backup, runtime, replace=True)

    assert result["restored"] is True
    assert (runtime / "operation-memory.json").read_text(encoding="utf-8") == '{"from":"backup"}'
    assert (runtime / "operational-safety.json").read_text(encoding="utf-8") == '{"from":"backup"}'
