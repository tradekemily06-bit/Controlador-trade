"""Safe backups for per-owner fiscal SQLite shards.

Shard names are opaque SHA-256 digests. This service never accepts tenant IDs
from callers, follows symlinks, overwrites backups, or modifies live databases.
"""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DIGEST = re.compile(r"[0-9a-f]{64}")


class TenantFiscalBackupService:
    def __init__(self, runtime_dir: str | Path, backup_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir).resolve()
        self.tenant_root = self.runtime_dir / "tenant-fiscal"
        self.backup_dir = Path(backup_dir).resolve()
        if self.backup_dir == self.runtime_dir or self.runtime_dir in self.backup_dir.parents:
            raise ValueError("backup directory must be outside runtime data directory")

    @staticmethod
    def _check(path: Path) -> None:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            rows = db.execute("PRAGMA quick_check").fetchall()
            if not rows or any(str(row[0]).lower() != "ok" for row in rows):
                raise sqlite3.DatabaseError("SQLite quick_check failed")
            if db.execute("PRAGMA foreign_key_check").fetchmany(1):
                raise sqlite3.IntegrityError("SQLite foreign_key_check failed")

    def _shards(self) -> list[tuple[str, Path]]:
        if not self.tenant_root.exists():
            return []
        if self.tenant_root.is_symlink() or not self.tenant_root.is_dir():
            raise ValueError("tenant fiscal root is unsafe")
        found: list[tuple[str, Path]] = []
        for shard_dir in sorted(self.tenant_root.iterdir()):
            if shard_dir.is_symlink() or not shard_dir.is_dir():
                raise ValueError("tenant fiscal shard directory is unsafe")
            for entry in sorted(shard_dir.iterdir()):
                digest = entry.stem
                if entry.suffix != ".sqlite3" or not _DIGEST.fullmatch(digest):
                    raise ValueError("unexpected file in tenant fiscal shard directory")
                if shard_dir.name != digest[:2]:
                    raise ValueError("tenant fiscal shard path does not match opaque digest")
                if entry.is_symlink() or not entry.is_file():
                    raise ValueError("tenant fiscal database is unsafe")
                if entry.resolve().parent != shard_dir.resolve():
                    raise ValueError("tenant fiscal database escaped shard directory")
                found.append((digest, entry))
        return found

    def backup(self) -> dict[str, Any]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        results = []
        try:
            shards = self._shards()
        except (OSError, ValueError) as exc:
            return {
                "provider": "TENANT_FISCAL_SQLITE_SHARDS",
                "status": "SOURCE_UNSAFE",
                "error_class": type(exc).__name__,
                "results": [],
                "execution_authorized": False,
            }
        for digest, source in shards:
            destination = self.backup_dir / f"tenant-fiscal-{digest}-{stamp}.sqlite3"
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=".tenant-fiscal-", suffix=".tmp",
                    dir=self.backup_dir, delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                source_uri = f"{source.resolve().as_uri()}?mode=ro"
                with sqlite3.connect(source_uri, uri=True, timeout=10) as src:
                    with sqlite3.connect(temporary, timeout=10) as dst:
                        src.backup(dst)
                self._check(temporary)
                os.link(temporary, destination)
                temporary.unlink()
                temporary = None
                results.append({
                    "owner_digest": digest,
                    "status": "BACKUP_CREATED",
                    "filename": destination.name,
                    "size_bytes": destination.stat().st_size,
                })
            except (OSError, sqlite3.Error) as exc:
                results.append({
                    "owner_digest": digest,
                    "status": "BACKUP_FAILED",
                    "error_class": type(exc).__name__,
                })
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return {
            "provider": "TENANT_FISCAL_SQLITE_SHARDS",
            "status": "NO_SHARDS_FOUND" if not shards else "COMPLETED",
            "results": results,
            "execution_authorized": False,
        }

    def verify_restore(self, filename: str) -> dict[str, Any]:
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("invalid tenant fiscal backup filename")
        match = re.fullmatch(
            r"tenant-fiscal-([0-9a-f]{64})-(\d{8}T\d{12}Z)\.sqlite3",
            filename,
        )
        if not match:
            raise ValueError("tenant fiscal backup filename is invalid")
        path = self.backup_dir / filename
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.backup_dir:
            raise ValueError("tenant fiscal backup is unsafe")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".tenant-fiscal-restore-", suffix=".sqlite3",
                dir=self.backup_dir, delete=False,
            ) as handle:
                temporary = Path(handle.name)
            uri = f"{path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=10) as src:
                with sqlite3.connect(temporary, timeout=10) as dst:
                    src.backup(dst)
            self._check(temporary)
            return {
                "status": "RESTORE_VALIDATED_IN_ISOLATION",
                "owner_digest": match.group(1),
                "backup_filename": filename,
                "live_database_modified": False,
                "execution_authorized": False,
            }
        except (OSError, sqlite3.Error) as exc:
            return {
                "status": "RESTORE_VALIDATION_FAILED",
                "error_class": type(exc).__name__,
                "live_database_modified": False,
                "execution_authorized": False,
            }
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
