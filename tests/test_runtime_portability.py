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



def test_create_backup_preserves_previous_archive_and_cleans_temp_on_write_failure(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text('{"safe":true}', encoding="utf-8")
    output = tmp_path / "runtime.zip"
    output.write_bytes(b"previous-valid-backup")

    class BrokenArchive:
        def __init__(self, *args, **kwargs):
            raise OSError("simulated archive creation failure")

    monkeypatch.setattr(portability.zipfile, "ZipFile", BrokenArchive)

    with pytest.raises(OSError, match="simulated archive creation failure"):
        portability.create_backup(source, output)

    assert output.read_bytes() == b"previous-valid-backup"
    assert list(tmp_path.glob(".runtime.zip.*.tmp")) == []



def test_verify_backup_rejects_payload_changed_without_manifest_update(tmp_path: Path):
    import json
    import zipfile

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text('{"safe":true}', encoding="utf-8")
    backup = tmp_path / "runtime.zip"
    portability.create_backup(source, backup)
    tampered = tmp_path / "tampered.zip"

    with zipfile.ZipFile(backup, "r") as original:
        manifest = original.read("manifest.json")
        with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as changed:
            changed.writestr("manifest.json", manifest)
            changed.writestr("operation-memory.json", b'{"safe":false}')

    with pytest.raises(ValueError, match="backup integrity failure"):
        portability.verify_backup(tampered)


def test_restore_rechecks_staged_payload_after_preflight(tmp_path: Path, monkeypatch):
    import zipfile

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text('{"trusted":true}', encoding="utf-8")
    backup = tmp_path / "runtime.zip"
    portability.create_backup(source, backup)
    original_verify = portability.verify_backup

    def verify_then_tamper(path):
        manifest = original_verify(path)
        rewritten = tmp_path / "rewritten.zip"
        with zipfile.ZipFile(path, "r") as original:
            with zipfile.ZipFile(rewritten, "w", compression=zipfile.ZIP_DEFLATED) as changed:
                for info in original.infolist():
                    data = original.read(info.filename)
                    if info.filename == "operation-memory.json":
                        data = b'{"trusted":false}'
                    changed.writestr(info.filename, data)
        os.replace(rewritten, path)
        return manifest

    monkeypatch.setattr(portability, "verify_backup", verify_then_tamper)
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    with pytest.raises(ValueError, match="backup integrity failure"):
        portability.restore_backup(backup, runtime)

    assert list(runtime.iterdir()) == []



def test_verify_backup_rejects_oversized_manifest(tmp_path: Path):
    import zipfile

    backup = tmp_path / "oversized-manifest.zip"
    with zipfile.ZipFile(backup, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", b" " * (1024 * 1024 + 1))

    with pytest.raises(ValueError, match="backup manifest is too large"):
        portability.verify_backup(backup)
