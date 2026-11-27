"""Safe, allowlisted SQLite backups for the standalone runtime.

Backups are explicit and opt-in. This service never restores, deletes, or
overwrites an existing backup. Production scheduling and off-host replication
must be configured separately.
"""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKUP_DATABASES = {
    "fiscal": "fiscal-reserve.sqlite3",
    "ecosystem_state": "ecosystem-state.sqlite3",
    "tenant_state": "tenant-state.sqlite3",
    "notification_outbox": "notification-outbox.sqlite3",
    "decision_memory": "decision-memory.sqlite3",
    "assistant_conversations": "assistant-conversations.sqlite3",
    "market_timeframe_monitor": "market-timeframe-monitor.sqlite3",
}


class SQLiteBackupService:
    def __init__(self, runtime_dir: str | Path, backup_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir).resolve()
        self.backup_dir = Path(backup_dir).resolve()
        if self.backup_dir == self.runtime_dir or self.runtime_dir in self.backup_dir.parents:
            raise ValueError("backup directory must be outside the runtime data directory")

    @staticmethod
    def _publish_exclusive(temporary: Path, destination: Path) -> None:
        """Atomically publish without replacing a backup created by another worker."""
        # Both paths are in the backup directory, so a hard link is same-filesystem.
        # Unlike exists()+replace(), link creation fails atomically if destination exists.
        os.link(temporary, destination)
        temporary.unlink()

    @staticmethod
    def _check(path: Path) -> None:
        """Check physical integrity and declared relational constraints."""
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            integrity_rows = db.execute("PRAGMA quick_check").fetchall()
            if not integrity_rows or any(str(row[0]).lower() != "ok" for row in integrity_rows):
                raise sqlite3.DatabaseError("backup integrity check failed")
            foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchmany(1)
            if foreign_key_errors:
                raise sqlite3.IntegrityError("backup foreign-key check failed")

    def backup(self, database_ids: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
        selected = tuple(BACKUP_DATABASES) if database_ids is None else tuple(database_ids)
        if not selected or len(set(selected)) != len(selected):
            raise ValueError("database selection must be non-empty and unique")
        unknown = sorted(set(selected) - set(BACKUP_DATABASES))
        if unknown:
            raise ValueError("unsupported database selection")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        results = []
        for database_id in selected:
            source_entry = self.runtime_dir / BACKUP_DATABASES[database_id]
            if source_entry.is_symlink():
                results.append({"id": database_id, "status": "SOURCE_UNSAFE"})
                continue
            source = source_entry.resolve()
            if source.parent != self.runtime_dir or not source.is_file():
                results.append({"id": database_id, "status": "SOURCE_MISSING"})
                continue
            destination = self.backup_dir / f"{database_id}-{stamp}.sqlite3"
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=f".{database_id}-", suffix=".tmp",
                    dir=self.backup_dir, delete=False
                ) as handle:
                    temporary = Path(handle.name)
                source_uri = f"{source.as_uri()}?mode=ro"
                with sqlite3.connect(source_uri, uri=True, timeout=10) as src:
                    with sqlite3.connect(temporary, timeout=10) as dst:
                        src.backup(dst)
                self._check(temporary)
                # Atomic exclusive publication: concurrent backups cannot overwrite.
                self._publish_exclusive(temporary, destination)
                temporary = None
                results.append({
                    "id": database_id,
                    "status": "BACKUP_CREATED",
                    "filename": destination.name,
                    "size_bytes": destination.stat().st_size,
                })
            except (OSError, sqlite3.Error) as exc:
                results.append({
                    "id": database_id,
                    "status": "BACKUP_FAILED",
                    "error_class": type(exc).__name__,
                })
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return {
            "provider": "SQLITE_ON_DEMAND",
            "backup_directory_configured": True,
            "results": results,
            "automatic_schedule": "NOT_CONFIGURED",
            "off_host_replication": "NOT_CONFIGURED",
            "restore_tested": False,
            "execution_authorized": False,
        }

    def verify_restore(self, database_id: str, filename: str) -> dict[str, Any]:
        """Validate a backup by restoring it to a temporary isolated SQLite DB.

        The live runtime database is never opened for writing or replaced.
        """
        if database_id not in BACKUP_DATABASES:
            raise ValueError("unsupported database selection")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("invalid backup filename")
        pattern = re.escape(database_id) + r"-\d{8}T\d{12}Z\.sqlite3"
        if not re.fullmatch(pattern, filename):
            raise ValueError("backup filename does not match the selected database")
        backup_path = self.backup_dir / filename
        if backup_path.is_symlink() or not backup_path.is_file():
            raise ValueError("backup must be an existing regular file")
        if backup_path.resolve().parent != self.backup_dir:
            raise ValueError("backup path is outside the authorized directory")

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{database_id}-restore-test-", suffix=".sqlite3",
                dir=self.backup_dir, delete=False,
            ) as handle:
                temporary = Path(handle.name)
            backup_uri = f"{backup_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(backup_uri, uri=True, timeout=10) as source:
                with sqlite3.connect(temporary, timeout=10) as restored:
                    source.backup(restored)
            self._check(temporary)
            return {
                "status": "RESTORE_VALIDATED_IN_ISOLATION",
                "database_id": database_id,
                "backup_filename": filename,
                "live_database_modified": False,
                "execution_authorized": False,
            }
        except (OSError, sqlite3.Error) as exc:
            return {
                "status": "RESTORE_VALIDATION_FAILED",
                "database_id": database_id,
                "error_class": type(exc).__name__,
                "live_database_modified": False,
                "execution_authorized": False,
            }
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
