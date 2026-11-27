"""Per-tenant fiscal repository factory.

This is a local SQLite isolation primitive. It is deliberately not wired into
remote request handling until identity, durable storage, backup/restore and
deployment controls are independently validated.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema
from security.tenant_context import TenantContext


_TENANT_FISCAL_DOMAIN = b"controlador-trading:tenant-fiscal-owner:v1:"


@dataclass(frozen=True)
class TenantFiscalRepositories:
    """Repositories and opaque owner key belonging to one verified subject."""

    owner_id: str
    database_path: str
    reserve: FiscalReserve
    foreign_pending: FiscalPendingQueue
    domestic_pending: FiscalDomesticPendingQueue


class TenantFiscalStoreFactory:
    """Resolve one separate local fiscal database from a trusted TenantContext."""

    def __init__(self, runtime_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir).expanduser().resolve()
        self.tenant_root = self.runtime_dir / "tenant-fiscal"
        self._lock = threading.RLock()
        self._stores: dict[str, TenantFiscalRepositories] = {}

    @staticmethod
    def _owner_digest(context: TenantContext) -> str:
        if not isinstance(context, TenantContext):
            raise TypeError("TenantContext confiável é obrigatório")
        material = context.key.encode("utf-8")
        return hashlib.sha256(_TENANT_FISCAL_DOMAIN + material).hexdigest()

    def get(self, context: TenantContext) -> TenantFiscalRepositories:
        """Return repositories isolated by tenant AND subject.

        The context must originate from the server's verified identity boundary;
        this class never accepts tenant/subject strings separately.
        """
        digest = self._owner_digest(context)
        owner_id = f"tenant:{digest}"
        with self._lock:
            cached = self._stores.get(digest)
            if cached is not None:
                return cached

            self.tenant_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.tenant_root.is_symlink():
                raise RuntimeError("diretório fiscal tenant não pode ser link simbólico")

            shard = self.tenant_root / digest[:2]
            shard.mkdir(mode=0o700, exist_ok=True)
            if shard.is_symlink():
                raise RuntimeError("partição fiscal tenant não pode ser link simbólico")

            database = shard / f"{digest}.sqlite3"
            if database.is_symlink():
                raise RuntimeError("arquivo fiscal tenant não pode ser link simbólico")
            if not database.resolve().is_relative_to(self.tenant_root.resolve()):
                raise RuntimeError("caminho fiscal tenant fora do diretório autorizado")

            migrate_fiscal_schema(str(database), trusted_owner_id=owner_id)
            repositories = TenantFiscalRepositories(
                owner_id=owner_id,
                database_path=str(database),
                reserve=FiscalReserve(str(database)),
                foreign_pending=FiscalPendingQueue(str(database)),
                domestic_pending=FiscalDomesticPendingQueue(str(database)),
            )
            self._stores[digest] = repositories
            return repositories


    def readiness(self) -> dict[str, object]:
        """Describe the local isolation primitive without implying production readiness."""
        return {
            "status": "LOCAL_TENANT_FISCAL_SHARDED_SQLITE_PRIMITIVE",
            "tenant_context_required": True,
            "separate_database_per_tenant_and_subject": True,
            "remote_request_wiring": "NOT_ENABLED",
            "production_durable": False,
            "backup_restore": "NOT_VERIFIED",
            "production_ready": False,
            "execution_authorized": False,
        }
