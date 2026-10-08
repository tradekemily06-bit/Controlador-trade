from __future__ import annotations
import hashlib, json, os, shutil, sqlite3, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

PORTABILITY_VERSION = 1
PORTABLE_FILES = ("operation-memory.json","operational-safety.json","execution-ledger.json","execution-lifecycle.json","automation-lifecycle.json","runtime-checkpoint.json","ecosystem-state.sqlite","decision-memory.sqlite","security-audit.sqlite")

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
        for member,(digest,size) in expected.items():
            data=archive.read(member)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest:
                raise ValueError(f"backup integrity failure: {member}")
    return manifest
def restore_backup(backup_file:str|Path,runtime_dir:str|Path,*,replace:bool=False)->dict[str,Any]:
    manifest=verify_backup(backup_file); runtime=Path(runtime_dir).resolve(); runtime.mkdir(parents=True,exist_ok=True)
    entries=[_safe_member(item["path"]) for item in manifest.get("files",[])]
    if not replace:
        conflicts=[name for name in entries if (runtime/name).exists()]
        if conflicts:
            raise FileExistsError(f"restore would overwrite existing state: {', '.join(conflicts)}")
    with zipfile.ZipFile(backup_file,"r") as archive, tempfile.TemporaryDirectory(prefix="controlador-restore-") as tmp:
        staged={}
        for name in entries:
            staged[name]=Path(tmp)/name
            staged[name].write_bytes(archive.read(name))
        for name in entries:
            destination=runtime/name
            temporary=destination.with_name(f".{destination.name}.restore.tmp")
            os.replace(staged[name],temporary)
            os.replace(temporary,destination)
    return {"restored":True,"runtime_dir":str(runtime),"files":entries,"machine_specific_configuration":"deployment-owned","secrets":"deployment-owned"}
