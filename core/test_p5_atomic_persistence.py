from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.durable_json import atomic_write_json


def test_atomic_write_replace_failure_preserves_previous_state(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text(json.dumps({"version": 1}), encoding="utf-8")

    def fail_replace(_temporary, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("core.durable_json.os.replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_json(target, {"version": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_write_cleanup_failure_does_not_mask_success(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    real_unlink = Path.unlink

    def fail_temp_cleanup(self: Path, *args, **kwargs):
        if self.parent == tmp_path and self.name.startswith(".state.json.") and self.name.endswith(".tmp"):
            raise OSError("simulated cleanup failure")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_temp_cleanup)
    atomic_write_json(target, {"version": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}


def test_atomic_write_json_encoding_failure_creates_no_partial_target(tmp_path):
    target = tmp_path / "state.json"
    target.write_text(json.dumps({"version": 1}), encoding="utf-8")

    class NotSerializable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": NotSerializable()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}
    assert not list(tmp_path.glob(".state.json.*.tmp"))


@pytest.mark.skipif(not hasattr(os, "O_DIRECTORY"), reason="directory fsync is not available")
def test_atomic_write_directory_fsync_failure_is_reported_as_ambiguous_commit(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    real_fsync = os.fsync
    calls = {"count": 0}

    def fail_directory_fsync(fd):
        calls["count"] += 1
        if calls["count"] >= 2:
            raise OSError("simulated directory fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr("core.durable_json.os.fsync", fail_directory_fsync)

    with pytest.raises(OSError, match="simulated directory fsync failure"):
        atomic_write_json(target, {"version": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}
