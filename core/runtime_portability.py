from __future__ import annotations
import hashlib, json, os, shutil, sqlite3, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import uuid
from typing import Any

PORTABILITY_VERSION = 1
PORTABLE_FILES = ("operation-memory.json","operational-safety.json","execution-ledger.json","execution-lifecycle.json","automation-lifecycle.json","runtime-checkpoint.json","demo-position-closes.json","demo-timed-exits.json","ecosystem-state.sqlite","decision-memory.sqlite","security-audit.sqlite","fiscal-reserve.sqlite3","assistant.sqlite3","latest-market-analysis.sqlite3")
SQLITE_SUFFIXES = frozenset({".sqlite", ".sqlite3", ".db"})

def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""): digest.update(chunk)
    return digest.hexdigest()

def _sqlite_snapshot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source_db=sqlite3.connect(source); target_db=sqlite3.connect(target)
    try:
        with target_db: source_db.backup(target_db)
    finally:
        target_db.close(); source_db.close()

def _copy_state(source: Path, target: Path) -> None:
    if source.suffix.lower() in SQLITE_SUFFIXES: _sqlite_snapshot(source,target)
    else:
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)

def create_backup(runtime_dir: str|Path, output_file: str|Path) -> dict[str,Any]:
    runtime=Path(runtime_dir).resolve(); output=Path(output_file).resolve()
    if not runtime.is_dir(): raise FileNotFoundError(f"runtime directory not found: {runtime}")
    if output.exists(): raise FileExistsError(f"backup already exists; refusing to overwrite: {output}")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="controlador-portability-") as tmp:
        stage=Path(tmp); staged=[]
        for name in PORTABLE_FILES:
            source=runtime/name
            if source.is_file():
                dest=stage/name; _copy_state(source,dest); staged.append((name,dest))
        if not staged:
            raise ValueError("runtime contains no portable state files; backup was not created")
        manifest={"format":"controlador-runtime-portable","version":PORTABILITY_VERSION,"created_at":datetime.now(timezone.utc).isoformat(),"runtime_identity":"portable-runtime-state","machine_specific_configuration":"excluded","secrets":"excluded","files":[{"path":n,"sha256":_sha256(p),"size":p.stat().st_size} for n,p in staged]}
        (stage/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
        # Use a unique staging file in the destination directory. A fixed
        # ``.tmp`` name could overwrite an unrelated file or collide with a
        # concurrent backup attempt; same-directory staging keeps os.replace
        # on the same volume for an atomic publication.
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(stage/"manifest.json","manifest.json")
                for name,path in staged: archive.write(path,name)
            os.replace(temporary,output)
        finally:
            temporary.unlink(missing_ok=True)
    try:
        verify_backup(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return manifest|{"backup":str(output)}

def _safe_member(name:str)->str:
    candidate=PurePosixPath(name)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts)!=1: raise ValueError("backup contains an unsafe path")
    if candidate.name not in PORTABLE_FILES: raise ValueError(f"backup contains an unsupported file: {name}")
    return candidate.name

def verify_backup(backup_file:str|Path)->dict[str,Any]:
    with zipfile.ZipFile(backup_file,"r") as archive:
        names=archive.namelist()
        if names.count("manifest.json") != 1:
            raise ValueError("backup manifest is missing or duplicated")
        member_names=[name for name in names if name!="manifest.json"]
        if len(member_names) != len(set(member_names)):
            raise ValueError("backup contains duplicate members")
        try:
            manifest=json.loads(archive.read("manifest.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("backup manifest is invalid") from exc
        if not isinstance(manifest,dict):
            raise ValueError("backup manifest is invalid")
        if manifest.get("format")!="controlador-runtime-portable" or manifest.get("version")!=PORTABILITY_VERSION:
            raise ValueError("unsupported backup format or version")
        entries=manifest.get("files")
        if not isinstance(entries,list):
            raise ValueError("backup manifest files are invalid")
        expected={}
        for item in entries:
            if not isinstance(item,dict) or set(item) != {"path","sha256","size"}:
                raise ValueError("backup manifest entry is invalid")
            if not isinstance(item["path"],str):
                raise ValueError("backup manifest entry is invalid")
            name=_safe_member(item["path"])
            digest=item["sha256"]
            size=item["size"]
            if (
                name in expected
                or not isinstance(digest,str)
                or len(digest)!=64
                or any(char not in "0123456789abcdefABCDEF" for char in digest)
                or not isinstance(size,int)
                or isinstance(size,bool)
                or size < 0
            ):
                raise ValueError("backup manifest entry is invalid")
            expected[name]=(digest,size)
        members=set(member_names)
        if members != set(expected):
            raise ValueError("backup contents do not match manifest")
        with tempfile.TemporaryDirectory(prefix="controlador-backup-verify-") as temp_dir:
            for member,(digest,size) in expected.items():
                data=archive.read(member)
                if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest:
                    raise ValueError(f"backup integrity failure: {member}")
                if Path(member).suffix.lower() in SQLITE_SUFFIXES:
                    staged_db = Path(temp_dir) / member
                    staged_db.write_bytes(data)
                    try:
                        with sqlite3.connect(staged_db) as connection:
                            integrity = connection.execute("PRAGMA integrity_check").fetchone()
                    except sqlite3.DatabaseError as exc:
                        raise ValueError(f"backup SQLite integrity failure: {member}") from exc
                    if not integrity or integrity[0] != "ok":
                        raise ValueError(f"backup SQLite integrity failure: {member}")
    return manifest
def restore_backup(backup_file:str|Path,runtime_dir:str|Path,*,replace:bool=False)->dict[str,Any]:
    manifest=verify_backup(backup_file); runtime=Path(runtime_dir).resolve(); runtime.mkdir(parents=True,exist_ok=True)
    entries=[_safe_member(item["path"]) for item in manifest.get("files",[])]
    if not replace:
        conflicts=[name for name in entries if (runtime/name).exists()]
        if conflicts:
            raise FileExistsError(f"restore would overwrite existing state: {', '.join(conflicts)}")
    # Stage beside the destination so os.replace stays on the same volume on Windows.
    rollback_copies: dict[str, Path] = {}
    replaced: list[str] = []
    with zipfile.ZipFile(backup_file,"r") as archive, tempfile.TemporaryDirectory(prefix=".controlador-restore-", dir=runtime) as tmp:
        stage = Path(tmp)
        incoming = stage / "incoming"
        incoming.mkdir()
        staged = {}
        for name in entries:
            staged[name] = incoming / name
            staged[name].write_bytes(archive.read(name))
        try:
            for name in entries:
                destination = runtime / name
                if destination.exists():
                    if not replace:
                        raise FileExistsError(f"restore would overwrite existing state: {name}")
                    if not destination.is_file():
                        raise ValueError(f"restore destination is not a regular file: {name}")
                    rollback_path = runtime / f".{destination.stem}.rollback-{uuid.uuid4().hex}{destination.suffix}"
                    _copy_state(destination, rollback_path)
                    rollback_copies[name] = rollback_path
                # The staged file already lives under ``runtime`` on the
                # destination volume, so publish it directly. Avoid a fixed
                # sibling .restore.tmp name that could clobber unrelated data.
                os.replace(staged[name], destination)
                replaced.append(name)
        except Exception as restore_error:
            rollback_failures: dict[str, str] = {}
            for name in reversed(replaced):
                destination = runtime / name
                if name in rollback_copies:
                    descriptor, rollback_name = tempfile.mkstemp(
                        prefix=f".{destination.name}.rollback-", dir=runtime
                    )
                    os.close(descriptor)
                    rollback_temporary = Path(rollback_name)
                    try:
                        _copy_state(rollback_copies[name], rollback_temporary)
                        os.replace(rollback_temporary, destination)
                    except Exception as rollback_error:
                        rollback_temporary.unlink(missing_ok=True)
                        rollback_failures[name] = str(rollback_error)
                else:
                    try:
                        destination.unlink(missing_ok=True)
                    except OSError as rollback_error:
                        rollback_failures[name] = str(rollback_error)
            for name, backup_path in rollback_copies.items():
                if name not in rollback_failures:
                    backup_path.unlink(missing_ok=True)
            if rollback_failures:
                details = "; ".join(
                    f"{name}: {error} (cópia anterior preservada em {rollback_copies.get(name, 'destino')})"
                    for name, error in rollback_failures.items()
                )
                raise RuntimeError(f"restore failed and rollback was incomplete: {details}") from restore_error
            raise
        else:
            for backup_path in rollback_copies.values():
                backup_path.unlink(missing_ok=True)
    return {"restored":True,"runtime_dir":str(runtime),"files":entries,"machine_specific_configuration":"deployment-owned","secrets":"deployment-owned"}
