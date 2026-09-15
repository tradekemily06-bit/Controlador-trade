from __future__ import annotations

from typing import Any, Protocol

from analysis.decision_record import DecisionRecord


class TenantScopedDecisionProvider(Protocol):
    """Durable provider contract already enforced by the production boundary."""

    def save(self, record: dict[str, Any], *, tenant_id: str, subject_id: str) -> None:
        ...

    def load(self, record_id: str, *, tenant_id: str, subject_id: str) -> dict[str, Any] | None:
        ...

    def list(self, *, tenant_id: str, subject_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        ...


class ProductionDecisionStore:
    """DecisionRecord adapter for the tenant-scoped production data plane.

    Unlike the local DecisionStore, this adapter never loads a global process
    history. Every operation requires both trusted tenant and subject scope.
    The provider is injected so the application remains database/vendor
    neutral; SQLite can be used for a single-instance deployment while a
    shared provider can implement the same contract for multi-instance SaaS.
    """

    def __init__(self, provider: TenantScopedDecisionProvider) -> None:
        self.provider = provider

    @staticmethod
    def _scope(*, tenant_id: str, subject_id: str) -> tuple[str, str]:
        tenant = str(tenant_id).strip()
        subject = str(subject_id).strip()
        if not tenant or not subject:
            raise ValueError("tenant_id and subject_id are required")
        return tenant, subject

    @staticmethod
    def _record(payload: dict[str, Any]) -> DecisionRecord:
        required = {
            "decision_id", "created_at", "signal", "score", "confirmed",
            "reason", "execution_allowed", "outcome", "symbol", "timeframe",
            "subject_id", "tenant_id",
        }
        missing = sorted(required.difference(payload))
        if missing:
            raise ValueError(f"production decision record missing fields: {', '.join(missing)}")
        return DecisionRecord(
            decision_id=str(payload["decision_id"]),
            created_at=str(payload["created_at"]),
            symbol=payload["symbol"],
            timeframe=payload["timeframe"],
            signal=str(payload["signal"]),
            score=float(payload["score"]),
            confirmed=bool(payload["confirmed"]),
            reason=str(payload["reason"]),
            execution_allowed=bool(payload["execution_allowed"]),
            outcome=payload["outcome"],
            subject_id=payload["subject_id"],
            tenant_id=payload["tenant_id"],
        )

    def save(self, record: DecisionRecord, *, tenant_id: str, subject_id: str) -> None:
        tenant, subject = self._scope(tenant_id=tenant_id, subject_id=subject_id)
        owned = record.with_owner(subject_id=subject, tenant_id=tenant)
        self.provider.save(owned.to_dict(), tenant_id=tenant, subject_id=subject)

    def load(self, decision_id: str, *, tenant_id: str, subject_id: str) -> DecisionRecord | None:
        tenant, subject = self._scope(tenant_id=tenant_id, subject_id=subject_id)
        payload = self.provider.load(str(decision_id).strip(), tenant_id=tenant, subject_id=subject)
        if payload is None:
            return None
        record = self._record(payload)
        if not record.owned_by(subject_id=subject, tenant_id=tenant):
            raise RuntimeError("production provider returned a record outside the requested scope")
        return record

    def list(self, *, tenant_id: str, subject_id: str, limit: int | None = None) -> list[DecisionRecord]:
        tenant, subject = self._scope(tenant_id=tenant_id, subject_id=subject_id)
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero when provided")
        records = [self._record(item) for item in self.provider.list(tenant_id=tenant, subject_id=subject, limit=limit)]
        if any(not record.owned_by(subject_id=subject, tenant_id=tenant) for record in records):
            raise RuntimeError("production provider returned records outside the requested scope")
        return records
