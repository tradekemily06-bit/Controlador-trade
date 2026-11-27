"""On-demand backup and isolated restore verification for one tenant fiscal DB.

No tenant enumeration, automatic scheduling, off-host replication or live restore.
The caller must supply a TenantContext resolved by the trusted identity layer.
"""
from __future__ import annotations

import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.sqlite_backup_service import SQLiteBackupService
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


_FISCAL_TABLES = (
    "fiscal_reserve_settings",
    "fiscal_reserve_entries",
    "fiscal_reserve_pending_foreign",
    "fiscal_pending_reviews",
    "fiscal_reserve_pending_domestic",
    "fiscal_domestic_pending_reviews",
)


class TenantFiscalBackupService:
    def __init__(
        self, store_factory: TenantFiscalStoreFactory, backup_dir: str | Path
    ) -> None:
        self.store_factory = store_factory
        self.backup_dir = Path(backup_dir).expanduser().resolve()
        runtime = store_factory.runtime_dir
        if self.backup_dir == runtime or runtime in self.backup_dir.parents:
            raise ValueError("backup directory must be outside runtime data directory")

    @staticmethod
    def _verified_owner_database(context: TenantContext, factory: TenantFiscalStoreFactory):
        if not isinstance(context, TenantContext):
            raise TypeError("TenantContext confiável é obrigatório")
        repositories = factory.get(context)
        source = Path(repositories.database_path)
        tenant_root = factory.tenant_root.resolve()
        if source.is_symlink() or not source.is_file():
            raise ValueError("tenant fiscal database is not a regular file")
        resolved = source.resolve()
        if not resolved.is_relative_to(tenant_root):
            raise ValueError("tenant fiscal database path is outside the managed root")
        digest = resolved.stem
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("tenant fiscal database identifier is invalid")
        return repositories, resolved, digest

    @staticmethod
    def _validate_restored_copy(path: Path, expected_owner_id: str) -> None:
        SQLiteBackupService._check(path)
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=10) as db:
            db.execute("PRAGMA foreign_keys = ON")
            tables = {
                row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = sorted(set(_FISCAL_TABLES) - tables)
            if missing:
                raise sqlite3.DatabaseError("restored fiscal schema is incomplete")
            for table in _FISCAL_TABLES:
                columns = {
                    row[1] for row in db.execute(f'PRAGMA table_info("{table}")').fetchall()
                }
                if "owner_id" not in columns:
                    raise sqlite3.DatabaseError("restored fiscal owner column is missing")
                owners = {
                    row[0] for row in db.execute(
                        f'SELECT DISTINCT owner_id FROM "{table}"'
                    ).fetchall()
                }
                if owners and owners != {expected_owner_id}:
                    raise sqlite3.DatabaseError("restored fiscal owner scope mismatch")
            violations = db.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise sqlite3.DatabaseError("restored fiscal foreign key check failed")

    def backup(self, context: TenantContext) -> dict[str, Any]:
        repositories, source, digest = self._verified_owner_database(
            context, self.store_factory
        )
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
            self._validate_restored_copy(temporary, repositories.owner_id)
            SQLiteBackupService._publish_exclusive(temporary, destination)
            temporary = None
            return {
                "status": "BACKUP_CREATED",
                "filename": destination.name,
                "size_bytes": destination.stat().st_size,
                "scope": "ONE_TENANT_AND_SUBJECT",
                "backup_integrity": "VERIFIED",
                "restore_tested": False,
                "automatic_schedule": "NOT_CONFIGURED",
                "off_host_replication": "NOT_CONFIGURED",
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

    def backup_all_managed_shards(self) -> dict[str, Any]:
        """Back up every managed opaque fiscal shard for the local maintenance worker.

        This privileged method accepts no tenant IDs and is not a request API.
        It enumerates only strict digest paths under the managed root, verifies
        each copied database's owner_id against its digest, and fails closed
        on unexpected files or symlinks.
        """
        root = self.store_factory.tenant_root
        if not root.exists():
            return {
                "status": "NO_TENANT_SHARDS",
                "results": [],
                "execution_authorized": False,
            }
        if root.is_symlink() or not root.is_dir():
            return {
                "status": "SOURCE_UNSAFE",
                "results": [],
                "execution_authorized": False,
            }
        shards: list[tuple[str, Path]] = []
        try:
            for shard_dir in sorted(root.iterdir()):
                if (
                    shard_dir.is_symlink()
                    or not shard_dir.is_dir()
                    or len(shard_dir.name) != 2
                    or any(c not in "0123456789abcdef" for c in shard_dir.name)
                ):
                    raise ValueError("unexpected tenant fiscal shard directory")
                for entry in sorted(shard_dir.iterdir()):
                    digest = entry.stem
                    if (
                        entry.suffix != ".sqlite3"
                        or len(digest) != 64
                        or any(c not in "0123456789abcdef" for c in digest)
                        or shard_dir.name != digest[:2]
                        or entry.is_symlink()
                        or not entry.is_file()
                        or entry.resolve().parent != shard_dir.resolve()
                    ):
                        raise ValueError("unexpected tenant fiscal shard file")
                    shards.append((digest, entry.resolve()))
        except (OSError, ValueError) as exc:
            return {
                "status": "SOURCE_UNSAFE",
                "error_class": type(exc).__name__,
                "results": [],
                "execution_authorized": False,
            }

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for digest, source in shards:
            expected_owner = f"tenant:{digest}"
            destination = self.backup_dir / (
                f"tenant-fiscal-{digest[:16]}-{stamp}.sqlite3"
            )
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=".tenant-fiscal-scheduled-", suffix=".tmp",
                    dir=self.backup_dir, delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                source_uri = f"{source.as_uri()}?mode=ro"
                with sqlite3.connect(source_uri, uri=True, timeout=10) as src:
                    with sqlite3.connect(temporary, timeout=10) as dst:
                        src.backup(dst)
                self._validate_restored_copy(temporary, expected_owner)
                SQLiteBackupService._publish_exclusive(temporary, destination)
                temporary = None
                results.append({
                    "owner_digest": digest,
                    "status": "BACKUP_CREATED",
                    "filename": destination.name,
                    "size_bytes": destination.stat().st_size,
                })
            except (OSError, sqlite3.Error, ValueError) as exc:
                results.append({
                    "owner_digest": digest,
                    "status": "BACKUP_FAILED",
                    "error_class": type(exc).__name__,
                })
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        overall = (
            "NO_TENANT_SHARDS" if not shards
            else "SUCCESS" if all(x["status"] == "BACKUP_CREATED" for x in results)
            else "PARTIAL_OR_FAILED"
        )
        return {
            "status": overall,
            "provider": "TENANT_FISCAL_SHARD_BACKUP",
            "results": results,
            "execution_authorized": False,
        }

    def verify_restore(self, context: TenantContext, filename: str) -> dict[str, Any]:
        """Restore a matching backup to a temporary isolated DB and validate it.

        The live tenant database is never replaced or modified.
        """
        repositories, _live_source, digest = self._verified_owner_database(
            context, self.store_factory
        )
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("nome de backup inválido")
        expected_prefix = f"tenant-fiscal-{digest[:16]}-"
        if (
            not filename.startswith(expected_prefix)
            or not filename.endswith(".sqlite3")
            or not re.fullmatch(r"[A-Za-z0-9-]+\.sqlite3", filename)
        ):
            raise ValueError("backup não pertence ao tenant e usuário autenticados")
        backup_path = self.backup_dir / filename
        if backup_path.is_symlink() or not backup_path.is_file():
            raise ValueError("backup não encontrado como arquivo regular")
        if backup_path.resolve().parent != self.backup_dir:
            raise ValueError("caminho de backup fora do diretório autorizado")

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".tenant-restore-test-", suffix=".sqlite3",
                dir=self.backup_dir, delete=False
            ) as handle:
                temporary = Path(handle.name)
            backup_uri = f"{backup_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(backup_uri, uri=True, timeout=10) as src:
                with sqlite3.connect(temporary, timeout=10) as dst:
                    src.backup(dst)
            self._validate_restored_copy(temporary, repositories.owner_id)
            return {
                "status": "RESTORE_VALIDATED_IN_ISOLATION",
                "scope": "ONE_TENANT_AND_SUBJECT",
                "live_database_modified": False,
                "backup_filename": filename,
                "execution_authorized": False,
            }
        except (OSError, sqlite3.Error) as exc:
            return {
                "status": "RESTORE_VALIDATION_FAILED",
                "error_class": type(exc).__name__,
                "scope": "ONE_TENANT_AND_SUBJECT",
                "live_database_modified": False,
                "execution_authorized": False,
            }
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
