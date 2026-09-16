from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from storage.production_boundary import ProductionStore, ProductionStoragePolicy
from storage.sqlite_production_store import SQLiteProductionStore


@dataclass(frozen=True)
class ProductionProviderConfig:
    """Explicit deployment configuration; never silently falls back to memory."""

    provider: str
    database_path: str | None
    multi_instance: bool

    @classmethod
    def from_environment(cls) -> "ProductionProviderConfig":
        provider = os.environ.get("CONTROLADOR_PRODUCTION_STORE", "").strip().lower()
        database_path = os.environ.get("CONTROLADOR_PRODUCTION_DB", "").strip() or None
        multi_instance = os.environ.get("CONTROLADOR_MULTI_INSTANCE", "").strip().lower() in {"1", "true", "yes", "on"}
        return cls(provider=provider, database_path=database_path, multi_instance=multi_instance)


def build_production_provider(config: ProductionProviderConfig | None = None) -> tuple[ProductionStore | None, ProductionStoragePolicy]:
    """Build only an explicitly configured durable provider.

    SQLite is deliberately rejected for a declared multi-instance deployment:
    it is a durable single-node provider, not a shared SaaS database. An absent
    provider returns a fail-closed policy and no store rather than silently using
    the process-local DecisionStore.
    """
    cfg = config or ProductionProviderConfig.from_environment()
    if cfg.provider == "sqlite":
        if not cfg.database_path:
            raise RuntimeError("CONTROLADOR_PRODUCTION_DB is required for sqlite production storage")
        if cfg.multi_instance:
            raise RuntimeError("sqlite production storage cannot be used for multi-instance SaaS")
        provider = SQLiteProductionStore(Path(cfg.database_path))
        return provider, ProductionStoragePolicy(required=True, provider_configured=True, tenant_scoped=True, durable=True)
    if cfg.provider in {"", "none", "unconfigured"}:
        return None, ProductionStoragePolicy(required=True, provider_configured=False, tenant_scoped=True, durable=False)
    raise RuntimeError(f"unsupported production storage provider: {cfg.provider}")
