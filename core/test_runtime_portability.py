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
