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
