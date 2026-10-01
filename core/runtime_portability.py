from __future__ import annotations
import hashlib, json, os, shutil, sqlite3, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
PORTABILITY_VERSION = 1
PORTABLE_FILES = ("operation-memory.json","operational-safety.json","execution-ledger.json","execution-lifecycle.json","runtime-checkpoint.json","ecosystem-state.sqlite","decision-memory.sqlite","security-audit.sqlite")
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
    if source.suffix.lower()==".sqlite": _sqlite_snapshot(source,target)
    else:
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
def create_backup(runtime_dir: str|Path, output_file: str|Path) -> dict[str,Any]:
    runtime=Path(runtime_dir).resolve(); output=Path(output_file).resolve()
    if not runtime.is_dir(): raise FileNotFoundError(f"runtime directory not found: {runtime}")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="controlador-portability-") as tmp:
        stage=Path(tmp); staged=[]
        for name in PORTABLE_FILES:
            source=runtime/name
            if source.is_file():
                dest=stage/name; _copy_state(source,dest); staged.append((name,dest))
        manifest={"format":"controlador-runtime-portable","version":PORTABILITY_VERSION,"created_at":datetime.now(timezone.utc).isoformat(),"runtime_identity":"portable-runtime-state","machine_specific_configuration":"excluded","secrets":"excluded","files":[{"path":n,"sha256":_sha256(p),"size":p.stat().st_size} for n,p in staged]}
        (stage/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
        temporary=output.with_suffix(output.suffix+".tmp")
        with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(stage/"manifest.json","manifest.json")
            for name,path in staged: archive.write(path,name)
        os.replace(temporary,output)
    return manifest|{"backup":str(output)}
def _safe_member(name:str)->str:
    candidate=PurePosixPath(name)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts)!=1: raise ValueError("backup contains an unsafe path")
    if candidate.name not in PORTABLE_FILES: raise ValueError(f"backup contains an unsupported file: {name}")
    return candidate.name
def verify_backup(backup_file:str|Path)->dict[str,Any]:
    with zipfile.ZipFile(backup_file,"r") as archive:
        manifest=json.loads(archive.read("manifest.json"))
        if manifest.get("format")!="controlador-runtime-portable" or manifest.get("version")!=PORTABILITY_VERSION: raise ValueError("unsupported backup format or version")
        expected={item["path"]:item["sha256"] for item in manifest.get("files",[])}
        for member in archive.namelist():
            if member=="manifest.json": continue
            _safe_member(member)
            if member not in expected or hashlib.sha256(archive.read(member)).hexdigest()!=expected[member]: raise ValueError(f"backup integrity failure: {member}")
    return manifest
def restore_backup(backup_file:str|Path,runtime_dir:str|Path,*,replace:bool=False)->dict[str,Any]:
    manifest=verify_backup(backup_file); runtime=Path(runtime_dir).resolve(); runtime.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(backup_file,"r") as archive:
        for item in manifest.get("files",[]):
            name=_safe_member(item["path"]); destination=runtime/name
            if destination.exists() and not replace: raise FileExistsError(f"restore would overwrite existing state: {name}")
            temporary=destination.with_name(f".{destination.name}.restore.tmp")
            with temporary.open("wb") as handle: handle.write(archive.read(name))
            os.replace(temporary,destination)
    return {"restored":True,"runtime_dir":str(runtime),"files":[x["path"] for x in manifest.get("files",[])],"machine_specific_configuration":"deployment-owned","secrets":"deployment-owned"}
