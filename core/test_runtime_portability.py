from pathlib import Path
import hashlib, json, sqlite3, zipfile, pytest
from core.runtime_portability import create_backup, restore_backup, verify_backup
def test_backup_round_trip(tmp_path:Path):
    runtime=tmp_path/"runtime"; runtime.mkdir()
    (runtime/"operation-memory.json").write_text('{"x":1}',encoding="utf-8")
    db=runtime/"decision-memory.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("create table decisions(id text primary key)"); con.execute("insert into decisions values ('d1')")
    module_databases = {
        "fiscal-reserve.sqlite3": ("fiscal_entries", "fiscal-1"),
        "assistant.sqlite3": ("messages", "assistant-1"),
        "latest-market-analysis.sqlite3": ("snapshots", "market-1"),
    }
    for filename, (table, value) in module_databases.items():
        with sqlite3.connect(runtime / filename) as con:
            con.execute(f"create table {table}(id text primary key)")
            con.execute(f"insert into {table} values (?)", (value,))
    backup=tmp_path/"state.zip"; manifest=create_backup(runtime,backup)
    backed_up = [x["path"] for x in manifest["files"]]
    assert "decision-memory.sqlite" in backed_up
    assert set(module_databases).issubset(backed_up)
    verify_backup(backup); restored=tmp_path/"restored"; assert restore_backup(backup,restored)["restored"]
    assert (restored/"operation-memory.json").read_text(encoding="utf-8")=='{"x":1}'
    with sqlite3.connect(restored/"decision-memory.sqlite") as con: assert con.execute("select id from decisions").fetchone()==("d1",)
    for filename, (table, value) in module_databases.items():
        with sqlite3.connect(restored / filename) as con:
            assert con.execute(f"select id from {table}").fetchone() == (value,)
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



def test_backup_rejects_corrupt_sqlite_database_even_when_manifest_hash_matches(tmp_path: Path):
    bad = tmp_path / "corrupt-sqlite.zip"
    payload = b"this is not a sqlite database"
    manifest = {
        "format": "controlador-runtime-portable",
        "version": 1,
        "files": [{
            "path": "fiscal-reserve.sqlite3",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }],
    }
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("fiscal-reserve.sqlite3", payload)
    with pytest.raises(ValueError, match="SQLite integrity failure"):
        verify_backup(bad)



def test_sqlite3_backup_captures_committed_wal_pages(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    database = runtime / "fiscal-reserve.sqlite3"
    writer = sqlite3.connect(database)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE fiscal_entries(reference TEXT PRIMARY KEY)")
        writer.execute("INSERT INTO fiscal_entries VALUES ('wal-committed-entry')")
        writer.commit()

        backup = tmp_path / "wal-state.zip"
        manifest = create_backup(runtime, backup)
        assert "fiscal-reserve.sqlite3" in [item["path"] for item in manifest["files"]]
    finally:
        writer.close()

    restored = tmp_path / "restored"
    restore_backup(backup, restored)
    with sqlite3.connect(restored / "fiscal-reserve.sqlite3") as connection:
        assert connection.execute("SELECT reference FROM fiscal_entries").fetchone() == (
            "wal-committed-entry",
        )



def test_backup_refuses_empty_runtime_directory(tmp_path: Path):
    runtime = tmp_path / "empty-runtime"
    runtime.mkdir()
    with pytest.raises(ValueError, match="no portable state files"):
        create_backup(runtime, tmp_path / "empty.zip")
    assert not (tmp_path / "empty.zip").exists()



def test_private_runtime_backup_directory_is_git_ignored():
    ignore_rules = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert ".runtime-backups/" in ignore_rules.splitlines()
