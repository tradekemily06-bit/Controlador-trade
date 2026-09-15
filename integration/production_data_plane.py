from __future__ import annotations

from dataclasses import dataclass

from analysis.decision_record import DecisionRecord
from storage.production_decision_store import ProductionDecisionStore
from storage.production_provider import ProductionProviderConfig, build_production_provider
from storage.production_boundary import ProductionStoragePolicy
from storage.scoped_state_store import SQLiteScopedStateStore


@dataclass(frozen=True)
class ProductionDataPlane:
    """Application-facing durable decision and auxiliary state plane.

    It never falls back to process memory for owned/public data. SQLite is only
    a single-instance provider; the deployment gate rejects multi-instance
    configuration until a shared provider is supplied.
    """

    store: ProductionDecisionStore
    policy: ProductionStoragePolicy
    state_store: SQLiteScopedStateStore

    @classmethod
    def from_config(cls, config: ProductionProviderConfig | None = None) -> "ProductionDataPlane | None":
        cfg = config or ProductionProviderConfig.from_environment()
        provider, policy = build_production_provider(cfg)
        if provider is None:
            return None
        if not policy.authorize_write(
            authenticated=True,
            tenant_id="configured",
            subject_id="configured",
        ):
            raise RuntimeError("production data plane provider is not authorized by its storage policy")
        if not cfg.database_path:
            raise RuntimeError("production database path is required for durable auxiliary state")
        return cls(
            store=ProductionDecisionStore(provider),
            policy=policy,
            state_store=SQLiteScopedStateStore(cfg.database_path),
        )

    @staticmethod
    def require_scope(*, tenant_id: str | None, subject_id: str | None) -> tuple[str, str]:
        tenant = str(tenant_id or "").strip()
        subject = str(subject_id or "").strip()
        if not tenant or not subject:
            raise PermissionError("trusted tenant and subject scope are required for production data")
        return tenant, subject

    def save(self, record: DecisionRecord, *, tenant_id: str | None, subject_id: str | None) -> None:
        tenant, subject = self.require_scope(tenant_id=tenant_id, subject_id=subject_id)
        self.store.save(record, tenant_id=tenant, subject_id=subject)

    def load(self, decision_id: str, *, tenant_id: str | None, subject_id: str | None) -> DecisionRecord | None:
        tenant, subject = self.require_scope(tenant_id=tenant_id, subject_id=subject_id)
        return self.store.load(decision_id, tenant_id=tenant, subject_id=subject)

    def list(self, *, tenant_id: str | None, subject_id: str | None, limit: int | None = None) -> list[DecisionRecord]:
        tenant, subject = self.require_scope(tenant_id=tenant_id, subject_id=subject_id)
        return self.store.list(tenant_id=tenant, subject_id=subject, limit=limit)

    def get_state(self, *, tenant_id: str | None, subject_id: str | None, namespace: str):
        tenant, subject = self.require_scope(tenant_id=tenant_id, subject_id=subject_id)
        return self.state_store.get(tenant_id=tenant, subject_id=subject, namespace=namespace)

    def put_state(self, *, tenant_id: str | None, subject_id: str | None, namespace: str, payload: object) -> None:
        tenant, subject = self.require_scope(tenant_id=tenant_id, subject_id=subject_id)
        self.state_store.put(tenant_id=tenant, subject_id=subject, namespace=namespace, payload=payload)
