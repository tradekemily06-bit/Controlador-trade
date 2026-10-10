from pathlib import Path
import sqlite3, zipfile, pytest
from core.runtime_portability import create_backup, restore_backup, verify_backup
def test_backup_round_trip(tmp_path:Path):
    runtime=tmp_path/"runtime"; runtime.mkdir()
    (runtime/"operation-memory.json").write_text('{"x":1}',encoding="utf-8")
    db=runtime/"decision-memory.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("create table decisions(id text primary key)"); con.execute("insert into decisions values ('d1')")
    backup=tmp_path/"state.zip"; manifest=create_backup(runtime,backup)
    assert "decision-memory.sqlite" in [x["path"] for x in manifest["files"]]
    verify_backup(backup); restored=tmp_path/"restored"; assert restore_backup(backup,restored)["restored"]
    assert (restored/"operation-memory.json").read_text(encoding="utf-8")=='{"x":1}'
    with sqlite3.connect(restored/"decision-memory.sqlite") as con: assert con.execute("select id from decisions").fetchone()==("d1",)
def test_restore_refuses_overwrite(tmp_path:Path):
    runtime=tmp_path/"runtime"; runtime.mkdir(); (runtime/"operation-memory.json").write_text("1")
    backup=tmp_path/"state.zip"; create_backup(runtime,backup); (runtime/"operation-memory.json").write_text("2")
    with pytest.raises(FileExistsError): restore_backup(backup,runtime)
def test_backup_rejects_unsafe_member(tmp_path:Path):
    bad=tmp_path/"bad.zip"
    with zipfile.ZipFile(bad,"w") as z:
        z.writestr("manifest.json",'{"format":"controlador-runtime-portable","version":1,"files":[{"path":"operation-memory.json","sha256":"x"}]}'); z.writestr("../evil","x")
    with pytest.raises(ValueError): verify_backup(bad)
def test_backup_rejects_manifest_missing_archive_member(tmp_path: Path):
    bad = tmp_path / "missing.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", '{"format":"controlador-runtime-portable","version":1,"files":[{"path":"operation-memory.json","sha256":"' + "0" * 64 + '","size":1}]}')
    with pytest.raises(ValueError, match="contents do not match manifest"): verify_backup(bad)
def test_backup_rejects_unlisted_archive_member(tmp_path: Path):
    bad = tmp_path / "extra.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", '{"format":"controlador-runtime-portable","version":1,"files":[]}')
        z.writestr("operation-memory.json", "x")
    with pytest.raises(ValueError, match="contents do not match manifest"): verify_backup(bad)
def test_restore_checks_all_conflicts_before_replacing_anything(tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    (source / "operation-memory.json").write_text("new", encoding="utf-8")
    (source / "operational-safety.json").write_text("new-safety", encoding="utf-8")
    backup = tmp_path / "state.zip"; create_backup(source, backup)
    target = tmp_path / "target"; target.mkdir()
    (target / "operational-safety.json").write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError): restore_backup(backup, target)
    assert not (target / "operation-memory.json").exists()
    assert (target / "operational-safety.json").read_text(encoding="utf-8") == "existing"


def test_backup_rejects_non_object_manifest(tmp_path: Path):
    bad = tmp_path / "manifest-list.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", "[]")
    with pytest.raises(ValueError, match="manifest is invalid"):
        verify_backup(bad)


def test_backup_rejects_boolean_file_size(tmp_path: Path):
    bad = tmp_path / "boolean-size.zip"
    manifest = (
        '{"format":"controlador-runtime-portable","version":1,"files":['
        '{"path":"operation-memory.json","sha256":"' + "0" * 64 + '","size":true}]}'
    )
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr("operation-memory.json", "x")
    with pytest.raises(ValueError, match="manifest entry is invalid"):
        verify_backup(bad)


def test_backup_rejects_duplicate_archive_members(tmp_path: Path):
    bad = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", '{"format":"controlador-runtime-portable","version":1,"files":[]}')
        archive.writestr("operation-memory.json", "x")
        with pytest.warns(UserWarning):
            archive.writestr("operation-memory.json", "x")
    with pytest.raises(ValueError, match="duplicate members"):
        verify_backup(bad)


def test_backup_rejects_duplicate_manifest(tmp_path: Path):
    bad = tmp_path / "duplicate-manifest.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", '{"format":"controlador-runtime-portable","version":1,"files":[]}')
        with pytest.warns(UserWarning):
            archive.writestr("manifest.json", '{"format":"controlador-runtime-portable","version":1,"files":[]}')
    with pytest.raises(ValueError, match="manifest is missing or duplicated"):
        verify_backup(bad)


def test_backup_rejects_duplicate_manifest_json_keys(tmp_path: Path):
    bad = tmp_path / "duplicate-json-key.zip"
    manifest = (
        '{"format":"controlador-runtime-portable","version":1,"version":2,"files":[]}'
    )
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", manifest)
    with pytest.raises(ValueError, match="manifest is invalid"):
        verify_backup(bad)


def test_backup_refuses_symlink_runtime_state(tmp_path: Path):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    outside = tmp_path / "outside.json"; outside.write_text("sensitive", encoding="utf-8")
    linked = runtime / "operation-memory.json"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable for this account/platform")
    with pytest.raises(ValueError, match="symbolic-link state file"):
        create_backup(runtime, tmp_path / "state.zip")
    assert not (tmp_path / "state.zip").exists()


def test_restore_rolls_back_committed_files_after_intermediate_replace_failure(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text("new-memory", encoding="utf-8")
    (source / "operational-safety.json").write_text("new-safety", encoding="utf-8")
    backup = tmp_path / "state.zip"
    create_backup(source, backup)

    target = tmp_path / "target"
    target.mkdir()
    (target / "operation-memory.json").write_text("old-memory", encoding="utf-8")
    (target / "operational-safety.json").write_text("old-safety", encoding="utf-8")

    original_replace = portability.os.replace
    failed = False

    def fail_once_on_second_incoming(source_path, destination_path):
        nonlocal failed
        if not failed and "incoming" in str(source_path) and str(source_path).endswith("operational-safety.json"):
            failed = True
            raise OSError("injected commit failure")
        return original_replace(source_path, destination_path)

    monkeypatch.setattr(portability.os, "replace", fail_once_on_second_incoming)
    with pytest.raises(OSError, match="injected commit failure"):
        restore_backup(backup, target, replace=True)

    assert (target / "operation-memory.json").read_text(encoding="utf-8") == "old-memory"
    assert (target / "operational-safety.json").read_text(encoding="utf-8") == "old-safety"


def test_restore_reports_incomplete_rollback_after_commit_failure(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text("new-memory", encoding="utf-8")
    (source / "operational-safety.json").write_text("new-safety", encoding="utf-8")
    backup = tmp_path / "state.zip"
    create_backup(source, backup)

    target = tmp_path / "target"
    target.mkdir()
    (target / "operation-memory.json").write_text("old-memory", encoding="utf-8")
    (target / "operational-safety.json").write_text("old-safety", encoding="utf-8")

    original_replace = portability.os.replace

    def fail_commit_and_rollback(source_path, destination_path):
        source_text = str(source_path)
        if "incoming" in source_text and source_text.endswith("operational-safety.json"):
            raise OSError("injected commit failure")
        if "rollback" in source_text:
            raise OSError("injected rollback failure")
        return original_replace(source_path, destination_path)

    monkeypatch.setattr(portability.os, "replace", fail_commit_and_rollback)
    with pytest.raises(RuntimeError, match="rollback incomplete"):
        restore_backup(backup, target, replace=True)



def test_backup_rejects_manifest_file_over_size_limit(tmp_path: Path):
    from core.runtime_portability import MAX_PORTABLE_FILE_BYTES

    bad = tmp_path / "oversized-member.zip"
    manifest = {
        "format": "controlador-runtime-portable",
        "version": 1,
        "files": [{
            "path": "operation-memory.json",
            "sha256": "0" * 64,
            "size": MAX_PORTABLE_FILE_BYTES + 1,
        }],
    }
    with zipfile.ZipFile(bad, "w") as archive:
        import json
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("operation-memory.json", b"x")
    with pytest.raises(ValueError, match="size limit"):
        verify_backup(bad)


def test_backup_rejects_total_size_limit_before_reading_members(tmp_path: Path):
    from core.runtime_portability import MAX_PORTABLE_FILE_BYTES, MAX_PORTABLE_TOTAL_BYTES

    bad = tmp_path / "oversized-total.zip"
    names = ["operation-memory.json", "operational-safety.json", "execution-ledger.json"]
    each_size = MAX_PORTABLE_TOTAL_BYTES // 2
    assert each_size <= MAX_PORTABLE_FILE_BYTES
    manifest = {
        "format": "controlador-runtime-portable",
        "version": 1,
        "files": [
            {"path": name, "sha256": "0" * 64, "size": each_size}
            for name in names
        ],
    }
    with zipfile.ZipFile(bad, "w") as archive:
        import json
        archive.writestr("manifest.json", json.dumps(manifest))
        for name in names:
            archive.writestr(name, b"x")
    with pytest.raises(ValueError, match="total size limit"):
        verify_backup(bad)



def test_backup_preserves_previous_archive_when_new_archive_verification_fails(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "operation-memory.json").write_text("current-state", encoding="utf-8")
    output = tmp_path / "state.zip"
    output.write_bytes(b"previous-known-backup")
    previous_bytes = output.read_bytes()

    def reject_archive(_path):
        raise ValueError("injected archive verification failure")

    monkeypatch.setattr(portability, "verify_backup", reject_archive)
    with pytest.raises(ValueError, match="injected archive verification failure"):
        create_backup(runtime, output)

    assert output.read_bytes() == previous_bytes
    assert not list(tmp_path.glob(".state.zip.*.tmp"))



def test_restore_rechecks_no_overwrite_conflicts_at_commit_time(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text("incoming-memory", encoding="utf-8")
    (source / "operational-safety.json").write_text("incoming-safety", encoding="utf-8")
    backup = tmp_path / "state.zip"
    create_backup(source, backup)

    target = tmp_path / "target"
    target.mkdir()
    original_link = portability.os.link
    injected = False

    def introduce_racing_destination(source_path, destination_path, *args, **kwargs):
        nonlocal injected
        source_text = str(source_path)
        if not injected and "incoming" in source_text and source_text.endswith("operation-memory.json"):
            injected = True
            (target / "operational-safety.json").write_text(
                "created-by-concurrent-process", encoding="utf-8"
            )
        return original_link(source_path, destination_path, *args, **kwargs)

    monkeypatch.setattr(portability.os, "link", introduce_racing_destination)
    with pytest.raises(FileExistsError, match="appeared during staging"):
        restore_backup(backup, target, replace=False)

    assert not (target / "operation-memory.json").exists()
    assert (target / "operational-safety.json").read_text(encoding="utf-8") == "created-by-concurrent-process"


def test_restore_no_replace_commit_is_atomic_against_racing_creator(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text("incoming", encoding="utf-8")
    backup = tmp_path / "state.zip"
    create_backup(source, backup)
    target = tmp_path / "target"
    target.mkdir()

    original_link = portability.os.link
    raced = False

    def create_destination_before_link(source_path, destination_path, *args, **kwargs):
        nonlocal raced
        if not raced and str(destination_path).endswith("operation-memory.json"):
            raced = True
            Path(destination_path).write_text("external-writer", encoding="utf-8")
        return original_link(source_path, destination_path, *args, **kwargs)

    monkeypatch.setattr(portability.os, "link", create_destination_before_link)
    with pytest.raises(FileExistsError, match="appeared during staging"):
        restore_backup(backup, target, replace=False)

    assert (target / "operation-memory.json").read_text(encoding="utf-8") == "external-writer"


def test_restore_rollback_preserves_concurrently_replaced_destination(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text("new-memory", encoding="utf-8")
    (source / "operational-safety.json").write_text("new-safety", encoding="utf-8")
    backup = tmp_path / "state.zip"
    create_backup(source, backup)

    target = tmp_path / "target"
    target.mkdir()
    (target / "operation-memory.json").write_text("old-memory", encoding="utf-8")
    (target / "operational-safety.json").write_text("old-safety", encoding="utf-8")

    original_replace = portability.os.replace
    failed = False

    def inject_external_change_then_fail(source_path, destination_path):
        nonlocal failed
        if (
            not failed
            and "incoming" in str(source_path)
            and str(source_path).endswith("operational-safety.json")
        ):
            failed = True
            (target / "operation-memory.json").write_text(
                "changed-by-concurrent-process", encoding="utf-8"
            )
            raise OSError("injected commit failure")
        return original_replace(source_path, destination_path)

    monkeypatch.setattr(portability.os, "replace", inject_external_change_then_fail)
    with pytest.raises(RuntimeError, match="destination (content )?changed concurrently; preserved"):
        restore_backup(backup, target, replace=True)

    assert (target / "operation-memory.json").read_text(encoding="utf-8") == "changed-by-concurrent-process"
    assert (target / "operational-safety.json").read_text(encoding="utf-8") == "old-safety"


def test_restore_replace_mode_does_not_overwrite_racing_new_file(tmp_path: Path, monkeypatch):
    import core.runtime_portability as portability

    source = tmp_path / "source"
    source.mkdir()
    (source / "operation-memory.json").write_text("incoming", encoding="utf-8")
    backup = tmp_path / "state.zip"
    create_backup(source, backup)
    target = tmp_path / "target"
    target.mkdir()

    original_link = portability.os.link
    raced = False

    def create_destination_before_link(source_path, destination_path, *args, **kwargs):
        nonlocal raced
        if not raced and str(destination_path).endswith("operation-memory.json"):
            raced = True
            Path(destination_path).write_text("external-writer", encoding="utf-8")
        return original_link(source_path, destination_path, *args, **kwargs)

    monkeypatch.setattr(portability.os, "link", create_destination_before_link)
    with pytest.raises(FileExistsError, match="appeared during staging"):
        restore_backup(backup, target, replace=True)

    assert (target / "operation-memory.json").read_text(encoding="utf-8") == "external-writer"

