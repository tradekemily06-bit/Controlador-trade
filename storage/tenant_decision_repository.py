from __future__ import annotations

from typing import Any, Protocol

from analysis.decision_record import DecisionRecord
from storage.production_boundary import ProductionStore


class TenantDecisionRepository(Protocol):
    """Provider-neutral tenant-and-subject-scoped decision persistence contract."""

    def save(self, record: DecisionRecord, *, tenant_id: str, subject_id: str) -> None:
        ...

    def load(self, decision_id: str, *, tenant_id: str, subject_id: str) -> DecisionRecord | None:
        ...

    def list(self, *, tenant_id: str, subject_id: str, limit: int = 100) -> list[DecisionRecord]:
        ...


class ProductionTenantDecisionRepository:
    """Translate DecisionRecord persistence through the production storage boundary.

    Production access is scoped by both tenant and subject. Tenant isolation alone is
    insufficient for personal decision history when multiple users share a tenant.
    Ownership metadata on the record must match the trusted scope supplied by the
    caller; callers cannot widen scope by putting another owner in the payload.
    """

    _IMMUTABLE_FIELDS = (
        "decision_id", "created_at", "symbol", "timeframe", "signal", "score",
        "confirmed", "reason", "execution_allowed", "subject_id", "tenant_id",
    )

    def __init__(self, store: ProductionStore) -> None:
        self.store = store

    @staticmethod
    def _validate_scope(tenant_id: str, subject_id: str) -> tuple[str, str]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not isinstance(subject_id, str) or not subject_id.strip():
            raise ValueError("subject_id is required")
        return tenant_id.strip(), subject_id.strip()

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
            subject_id=payload.get("subject_id"),
            tenant_id=payload.get("tenant_id"),
        )

    @classmethod
    def _immutable_values(cls, record: DecisionRecord) -> tuple[Any, ...]:
        payload = record.to_dict()
        return tuple(payload[field] for field in cls._IMMUTABLE_FIELDS)

    def save(self, record: DecisionRecord, *, tenant_id: str, subject_id: str) -> None:
        tenant, subject = self._validate_scope(tenant_id, subject_id)
        if record.tenant_id != tenant or record.subject_id != subject:
            raise PermissionError("decision ownership does not match trusted scope")

        existing_payload = self.store.load(record.decision_id, tenant_id=tenant, subject_id=subject)
        if existing_payload is not None:
            existing = self._to_record(existing_payload)
            if existing.tenant_id != tenant or existing.subject_id != subject:
                raise PermissionError("stored decision ownership does not match trusted scope")
            if self._immutable_values(existing) != self._immutable_values(record):
                raise PermissionError("decision core fields are immutable")
        self.store.save(record.to_dict(), tenant_id=tenant, subject_id=subject)

    def load(self, decision_id: str, *, tenant_id: str, subject_id: str) -> DecisionRecord | None:
        tenant, subject = self._validate_scope(tenant_id, subject_id)
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id is required")
        payload = self.store.load(decision_id.strip(), tenant_id=tenant, subject_id=subject)
        if payload is None:
            return None
        record = self._to_record(payload)
        if record.tenant_id != tenant or record.subject_id != subject:
            raise PermissionError("stored decision ownership does not match trusted scope")
        return record

    def list(self, *, tenant_id: str, subject_id: str, limit: int = 100) -> list[DecisionRecord]:
        tenant, subject = self._validate_scope(tenant_id, subject_id)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be greater than zero")
        records = [self._to_record(item) for item in self.store.list(tenant_id=tenant, subject_id=subject, limit=limit)]
        for record in records:
            if record.tenant_id != tenant or record.subject_id != subject:
                raise PermissionError("stored decision ownership does not match trusted scope")
        return records
