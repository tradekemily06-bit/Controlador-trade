from __future__ import annotations

from dataclasses import dataclass

from analysis.decision_record import DecisionRecord
from storage.production_decision_store import ProductionDecisionStore
from storage.production_provider import ProductionProviderConfig, build_production_provider
from storage.production_boundary import ProductionStoragePolicy


@dataclass(frozen=True)
class ProductionDataPlane:
    """Application-facing durable decision data plane.

    The facade makes the production storage dependency explicit at the
    application boundary. It never falls back to DecisionStore or process
    memory. A missing provider therefore remains a hard configuration error
    for owned/public data rather than becoming a silent local-data fallback.
    """

    store: ProductionDecisionStore
    policy: ProductionStoragePolicy

    @classmethod
    def from_config(cls, config: ProductionProviderConfig | None = None) -> "ProductionDataPlane | None":
        provider, policy = build_production_provider(config)
        if provider is None:
            return None
        if not policy.authorize_write(authenticated=True, tenant_id="configured"):
            raise RuntimeError("production data plane provider is not authorized by its storage policy")
        return cls(store=ProductionDecisionStore(provider), policy=policy)

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

    def list(self, *, tenant_id: str | None, subject_id: str | None, limit: int = 100) -> list[DecisionRecord]:
        tenant, subject = self.require_scope(tenant_id=tenant_id, subject_id=subject_id)
        return self.store.list(tenant_id=tenant, subject_id=subject, limit=limit)
