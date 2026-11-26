"""On-demand backup for a single verified tenant's fiscal database.

This service does not enumerate tenants and cannot restore or replicate data.
The caller must supply the TenantContext resolved by the trusted identity layer.
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.sqlite_backup_service import SQLiteBackupService
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


class TenantFiscalBackupService:
    def __init__(
        self, store_factory: TenantFiscalStoreFactory, backup_dir: str | Path
    ) -> None:
        self.store_factory = store_factory
        self.backup_dir = Path(backup_dir).expanduser().resolve()
        runtime = store_factory.runtime_dir
        if self.backup_dir == runtime or runtime in self.backup_dir.parents:
            raise ValueError("backup directory must be outside runtime data directory")

    def backup(self, context: TenantContext) -> dict[str, Any]:
        if not isinstance(context, TenantContext):
            raise TypeError("TenantContext confiável é obrigatório")
        repositories = self.store_factory.get(context)
        source = Path(repositories.database_path).resolve()
        tenant_root = self.store_factory.tenant_root.resolve()
        if source.is_symlink() or not source.is_file():
            raise ValueError("tenant fiscal database is not a regular file")
        if not source.is_relative_to(tenant_root):
            raise ValueError("tenant fiscal database path is outside the managed root")

        digest = source.stem
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("tenant fiscal database identifier is invalid")

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.backup_dir / f"tenant-fiscal-{digest[:16]}-{stamp}.sqlite3"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".tenant-fiscal-", suffix=".tmp",
                dir=self.backup_dir, delete=False
            ) as handle:
                temporary = Path(handle.name)
            source_uri = f"{source.as_uri()}?mode=ro"
            with sqlite3.connect(source_uri, uri=True, timeout=10) as src:
                with sqlite3.connect(temporary, timeout=10) as dst:
                    src.backup(dst)
            SQLiteBackupService._check(temporary)
            SQLiteBackupService._publish_exclusive(temporary, destination)
            temporary = None
            return {
                "status": "BACKUP_CREATED",
                "filename": destination.name,
                "size_bytes": destination.stat().st_size,
                "scope": "ONE_TENANT_AND_SUBJECT",
                "automatic_schedule": "NOT_CONFIGURED",
                "off_host_replication": "NOT_CONFIGURED",
                "restore_tested": False,
                "execution_authorized": False,
            }
        except (OSError, sqlite3.Error) as exc:
            return {
                "status": "BACKUP_FAILED",
                "error_class": type(exc).__name__,
                "scope": "ONE_TENANT_AND_SUBJECT",
                "restore_tested": False,
                "execution_authorized": False,
            }
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
