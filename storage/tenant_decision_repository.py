from __future__ import annotations

from typing import Any, Protocol

from analysis.decision_record import DecisionRecord
from storage.production_boundary import ProductionStore


class TenantDecisionRepository(Protocol):
    """Provider-neutral tenant-scoped decision persistence contract."""

    def save(self, record: DecisionRecord, *, tenant_id: str) -> None:
        ...

    def load(self, decision_id: str, *, tenant_id: str) -> DecisionRecord | None:
        ...

    def list(self, *, tenant_id: str, limit: int = 100) -> list[DecisionRecord]:
        ...


class ProductionTenantDecisionRepository:
    """Translate DecisionRecord persistence through the production storage boundary.

    Tenant identity is mandatory on every operation. The repository never accepts a
    global decision lookup, so a production caller cannot accidentally cross tenant
    boundaries by using only a decision id.
    """

    def __init__(self, store: ProductionStore) -> None:
        self.store = store

    @staticmethod
    def _validate_tenant(tenant_id: str) -> str:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        return tenant_id.strip()

    @staticmethod
    def _to_record(payload: dict[str, Any]) -> DecisionRecord:
        return DecisionRecord(
            decision_id=str(payload["decision_id"]),
            created_at=str(payload["created_at"]),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
            signal=str(payload["signal"]),
            score=float(payload["score"]),
            confirmed=bool(payload["confirmed"]),
            reason=str(payload["reason"]),
            execution_allowed=bool(payload.get("execution_allowed", False)),
            outcome=payload.get("outcome"),
        )

    def save(self, record: DecisionRecord, *, tenant_id: str) -> None:
        tenant = self._validate_tenant(tenant_id)
        self.store.save(record.to_dict(), tenant_id=tenant)

    def load(self, decision_id: str, *, tenant_id: str) -> DecisionRecord | None:
        tenant = self._validate_tenant(tenant_id)
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id is required")
        payload = self.store.load(decision_id.strip(), tenant_id=tenant)
        return None if payload is None else self._to_record(payload)

    def list(self, *, tenant_id: str, limit: int = 100) -> list[DecisionRecord]:
        tenant = self._validate_tenant(tenant_id)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be greater than zero")
        return [self._to_record(item) for item in self.store.list(tenant_id=tenant, limit=limit)]
