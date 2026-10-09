from __future__ import annotations
import hashlib, json, os, shutil, sqlite3, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

PORTABILITY_VERSION = 1
PORTABLE_FILES = ("operation-memory.json","operational-safety.json","execution-ledger.json","execution-lifecycle.json","automation-lifecycle.json","runtime-checkpoint.json","ecosystem-state.sqlite","decision-memory.sqlite","security-audit.sqlite")
# Defensive limits for imported archives and runtime state. These allow large
# SQLite histories while bounding accidental/malicious archive expansion.
MAX_PORTABLE_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PORTABLE_TOTAL_BYTES = 4 * 1024 * 1024 * 1024

def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""): digest.update(chunk)
    return digest.hexdigest()

def _hash_archive_member(archive: zipfile.ZipFile, member: str, expected_size: int) -> tuple[str, int]:
    """Hash a ZIP member incrementally; never load an entire runtime database into RAM."""
    digest=hashlib.sha256()
    size=0
    with archive.open(member,"r") as source:
        for chunk in iter(lambda: source.read(1024*1024), b""):
            size += len(chunk)
            if size > expected_size:
                raise ValueError(f"backup integrity failure: {member}")
            digest.update(chunk)
    return digest.hexdigest(), size

def _copy_archive_member(archive: zipfile.ZipFile, member: str, target: Path, expected_digest: str, expected_size: int) -> None:
    """Stage and verify the exact bytes that will be restored, protecting against archive changes after preflight."""
    digest=hashlib.sha256()
    size=0
    target.parent.mkdir(parents=True,exist_ok=True)
    with archive.open(member,"r") as source, target.open("wb") as destination:
        for chunk in iter(lambda: source.read(1024*1024), b""):
            size += len(chunk)
            if size > expected_size:
                raise ValueError(f"backup integrity failure: {member}")
            digest.update(chunk)
            destination.write(chunk)
    if size != expected_size or digest.hexdigest() != expected_digest:
        target.unlink(missing_ok=True)
        raise ValueError(f"backup integrity failure: {member}")

def _sqlite_snapshot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(source)
    try:
        target_db = sqlite3.connect(target)
        try:
            with target_db:
                source_db.backup(target_db)
        finally:
            target_db.close()
    finally:
        source_db.close()

def _copy_state(source: Path, target: Path) -> None:
    if source.suffix.lower()==".sqlite": _sqlite_snapshot(source,target)
    else:
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)

def create_backup(runtime_dir: str|Path, output_file: str|Path) -> dict[str,Any]:
    # Do not resolve an existing output symlink: that would silently redirect
    # publication to another file and defeat the caller's chosen destination.
    requested_runtime=Path(runtime_dir).expanduser()
    if requested_runtime.is_symlink():
        raise ValueError(f"runtime backup refuses symbolic-link source directory: {requested_runtime}")
    requested_output=Path(output_file).expanduser()
    if requested_output.is_symlink():
        raise ValueError(f"backup output refuses symbolic-link destination: {requested_output}")
    runtime=requested_runtime.resolve(); output=requested_output.resolve()
    if not runtime.is_dir(): raise FileNotFoundError(f"runtime directory not found: {runtime}")
    if output in {runtime/name for name in PORTABLE_FILES}:
        raise ValueError("backup output must not overwrite a portable runtime state file")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="controlador-portability-") as tmp:
        stage=Path(tmp); staged=[]
        staged_total = 0
        for name in PORTABLE_FILES:
            source=runtime/name
            if source.is_symlink():
                raise ValueError(f"runtime backup refuses symbolic-link state file: {name}")
            if source.is_file():
                source_size = source.stat().st_size
                if source_size > MAX_PORTABLE_FILE_BYTES:
                    raise ValueError(f"runtime state file exceeds portability size limit: {name}")
                staged_total += source_size
                if staged_total > MAX_PORTABLE_TOTAL_BYTES:
                    raise ValueError("runtime state exceeds portability total size limit")
                dest=stage/name; _copy_state(source,dest)
                dest_size = dest.stat().st_size
                if dest_size > MAX_PORTABLE_FILE_BYTES:
                    raise ValueError(f"runtime state file exceeds portability size limit: {name}")
                staged_total += dest_size - source_size
                if staged_total > MAX_PORTABLE_TOTAL_BYTES:
                    raise ValueError("runtime state exceeds portability total size limit")
                staged.append((name,dest))
        if sum(path.stat().st_size for _, path in staged) > MAX_PORTABLE_TOTAL_BYTES:
            raise ValueError("runtime state exceeds portability total size limit")
        if not staged:
            raise ValueError("runtime backup refused: no portable state files were found")
        manifest={"format":"controlador-runtime-portable","version":PORTABILITY_VERSION,"created_at":datetime.now(timezone.utc).isoformat(),"runtime_identity":"portable-runtime-state","machine_specific_configuration":"excluded","secrets":"excluded","files":[{"path":n,"sha256":_sha256(p),"size":p.stat().st_size} for n,p in staged]}
        (stage/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
        # Unique temp file beside destination: concurrent backups cannot share it.
        temp_handle=tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.",suffix=".tmp",dir=output.parent,delete=False
        )
        temporary=Path(temp_handle.name)
        temp_handle.close()
        try:
            with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(stage/"manifest.json","manifest.json")
                for name,path in staged: archive.write(path,name)
            # Never publish a backup until the exact archive on disk passes verification.
            verify_backup(temporary)
            os.replace(temporary,output)
        finally:
            temporary.unlink(missing_ok=True)
    return manifest|{"backup":str(output)}

def _safe_member(name:str)->str:
    candidate=PurePosixPath(name)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts)!=1: raise ValueError("backup contains an unsafe path")
    if candidate.name not in PORTABLE_FILES: raise ValueError(f"backup contains an unsupported file: {name}")
    return candidate.name

class _DuplicateManifestKeyError(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON objects instead of silently keeping the last duplicate key."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateManifestKeyError(f"backup manifest contains duplicate key: {key}")
        result[key] = value
    return result


def verify_backup(backup_file:str|Path)->dict[str,Any]:
    with zipfile.ZipFile(backup_file,"r") as archive:
        names=archive.namelist()
        if names.count("manifest.json") != 1:
            raise ValueError("backup manifest is missing or duplicated")
        member_names=[name for name in names if name!="manifest.json"]
        if len(member_names) != len(set(member_names)):
            raise ValueError("backup contains duplicate members")
        try:
            manifest_info=archive.getinfo("manifest.json")
            # The manifest only describes at most PORTABLE_FILES; bound its
            # parsing cost instead of trusting a potentially huge ZIP member.
            if manifest_info.file_size > 1024 * 1024:
                raise ValueError("backup manifest is too large")
            with archive.open("manifest.json","r") as manifest_stream:
                manifest_bytes=manifest_stream.read(1024 * 1024 + 1)
            if len(manifest_bytes) > 1024 * 1024:
                raise ValueError("backup manifest is too large")
            manifest=json.loads(manifest_bytes, object_pairs_hook=_reject_duplicate_json_keys)
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError, _DuplicateManifestKeyError) as exc:
            raise ValueError("backup manifest is invalid") from exc
        if not isinstance(manifest,dict):
            raise ValueError("backup manifest is invalid")
        version = manifest.get("version")
        # bool is a subclass of int in Python (True == 1); reject it explicitly
        # so a malformed manifest cannot pass the format-version gate.
        if (
            manifest.get("format") != "controlador-runtime-portable"
            or type(version) is not int
            or version != PORTABILITY_VERSION
        ):
            raise ValueError("unsupported backup format or version")
        entries=manifest.get("files")
        if not isinstance(entries,list):
            raise ValueError("backup manifest files are invalid")
        expected={}
        total_size = 0
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
                or size > MAX_PORTABLE_FILE_BYTES
            ):
                raise ValueError("backup manifest entry is invalid or exceeds size limit")
            total_size += size
            if total_size > MAX_PORTABLE_TOTAL_BYTES:
                raise ValueError("backup exceeds portability total size limit")
            expected[name]=(digest.lower(),size)
        members=set(member_names)
        if members != set(expected):
            raise ValueError("backup contents do not match manifest")
        if not entries:
            raise ValueError("backup manifest files are invalid or empty")
        for member,(digest,size) in expected.items():
            info=archive.getinfo(member)
            if info.file_size != size:
                raise ValueError(f"backup integrity failure: {member}")
            actual_digest,actual_size=_hash_archive_member(archive,member,size)
            if actual_size!=size or actual_digest!=digest:
                raise ValueError(f"backup integrity failure: {member}")
    return manifest

def restore_backup(backup_file:str|Path,runtime_dir:str|Path,*,replace:bool=False)->dict[str,Any]:
    requested_backup=Path(backup_file).expanduser()
    if requested_backup.is_symlink():
        raise ValueError(f"restore refuses symbolic-link backup source: {requested_backup}")
    backup=requested_backup.resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"runtime backup not found: {backup}")
    requested_runtime=Path(runtime_dir).expanduser()
    if requested_runtime.is_symlink():
        raise ValueError(f"restore refuses symbolic-link runtime directory: {requested_runtime}")
    manifest=verify_backup(backup)
    runtime=requested_runtime.resolve()
    runtime.mkdir(parents=True,exist_ok=True)
    entries=[_safe_member(item["path"]) for item in manifest.get("files",[])]
    expected={item["path"]:(item["sha256"].lower(),item["size"]) for item in manifest.get("files",[])}
    symlinks=[name for name in entries if (runtime/name).is_symlink()]
    if symlinks:
        raise ValueError(f"restore refuses symbolic-link destinations: {', '.join(symlinks)}")
    if not replace:
        conflicts=[name for name in entries if (runtime/name).exists()]
        if conflicts:
            raise FileExistsError(f"restore would overwrite existing state: {', '.join(conflicts)}")

    # Stage incoming data and rollback copies on the destination filesystem.
    # Verify staged bytes too, so changed/corrupt archives never reach commit.
    with zipfile.ZipFile(backup,"r") as archive, tempfile.TemporaryDirectory(
        prefix=".controlador-restore-",dir=runtime
    ) as tmp:
        stage=Path(tmp)
        incoming={}
        originals={}
        existed={}
        for name in entries:
            incoming[name]=stage/"incoming"/name
            digest,size=expected[name]
            _copy_archive_member(archive,name,incoming[name],digest,size)
            destination=runtime/name
            existed[name]=destination.exists()
            if existed[name]:
                if not destination.is_file():
                    raise ValueError(f"restore refuses non-file destination: {name}")
                originals[name]=stage/"originals"/name
                originals[name].parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(destination,originals[name])

        committed=[]
        witnesses={}
        try:
            for name in entries:
                destination = runtime/name
                if destination.is_symlink():
                    raise ValueError(
                        f"restore refuses symbolic-link destination at commit: {name}"
                    )
                if not replace:
                    # os.replace() overwrites on POSIX and can race with a
                    # concurrent creator even after an exists() check.
                    # A same-filesystem hard link is an atomic no-clobber
                    # create on supported Windows/NTFS and POSIX filesystems.
                    try:
                        os.link(incoming[name], destination)
                    except FileExistsError as exc:
                        raise FileExistsError(
                            f"restore destination appeared during staging: {name}"
                        ) from exc
                    # Keep incoming staged until commit completes. Its inode
                    # is the ownership witness used during a safe rollback.
                    witnesses[name] = incoming[name]
                    committed.append(name)
                    continue

                # Keep a hard-link witness to the exact bytes installed. If
                # another process replaces or edits the destination before
                # rollback, preserve that concurrent change rather than
                # blindly restoring over it.
                witness = stage/"committed"/name
                witness.parent.mkdir(parents=True, exist_ok=True)
                os.link(incoming[name], witness)
                witnesses[name] = witness
                os.replace(incoming[name], destination)
                committed.append(name)
        except Exception as commit_error:
            rollback_errors=[]
            for name in reversed(committed):
                destination=runtime/name
                witness=witnesses[name]
                try:
                    if destination.is_symlink() or not destination.exists() or not os.path.samefile(destination, witness):
                        rollback_errors.append(
                            f"{name}: destination changed concurrently; preserved"
                        )
                        continue
                    # Detect in-place edits too; samefile alone only detects
                    # replacement of the destination's directory entry.
                    expected_digest, _ = expected[name]
                    if _sha256(destination) != expected_digest:
                        rollback_errors.append(
                            f"{name}: destination content changed concurrently; preserved"
                        )
                        continue
                    if existed[name]:
                        rollback_temp=stage/"rollback"/name
                        rollback_temp.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(originals[name],rollback_temp)
                        os.replace(rollback_temp,destination)
                    else:
                        destination.unlink()
                except Exception as rollback_error:
                    rollback_errors.append(f"{name}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(
                    f"restore failed ({commit_error}); rollback incomplete: "
                    + "; ".join(rollback_errors)
                ) from commit_error
            raise
    return {"restored":True,"runtime_dir":str(runtime),"files":entries,
            "machine_specific_configuration":"deployment-owned","secrets":"deployment-owned"}
