from __future__ import annotations

from typing import Any

from analysis.decision_record import DecisionRecord
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext


class TenantScopedDecisionMemory:
    """Decision history addressed to one verified tenant and subject.

    This is deliberately separate from the legacy global DecisionStore.
    It never imports or assigns historical global decisions to a user.
    """

    _INDEX_KEY = "analysis:decision-index"
    _RECORD_PREFIX = "analysis:decision:"

    def __init__(self, storage: SQLiteTenantStorage) -> None:
        if not isinstance(storage, SQLiteTenantStorage):
            raise TypeError("SQLiteTenantStorage is required")
        self.storage = storage

    @staticmethod
    def _context(context: TenantContext | None) -> TenantContext:
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
        return context

    @staticmethod
    def _record(value: Any) -> DecisionRecord:
        if not isinstance(value, dict):
            raise ValueError("stored decision has an invalid shape")
        try:
            record = DecisionRecord(
                decision_id=value["decision_id"],
                created_at=value["created_at"],
                symbol=value.get("symbol"),
                timeframe=value.get("timeframe"),
                signal=value["signal"],
                score=float(value["score"]),
                confirmed=value["confirmed"],
                reason=value["reason"],
                execution_allowed=value.get("execution_allowed", False),
                outcome=value.get("outcome"),
                outcome_source=value.get("outcome_source", "MANUAL_STUDY"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("stored decision failed domain validation") from exc
        if (
            not isinstance(record.decision_id, str) or not record.decision_id.strip()
            or not isinstance(record.created_at, str) or not record.created_at.strip()
            or not isinstance(record.signal, str) or not record.signal.strip()
            or not isinstance(record.reason, str)
            or not isinstance(record.confirmed, bool)
            or not isinstance(record.execution_allowed, bool)
            or record.execution_allowed
            or (record.outcome is not None and record.outcome not in {"WIN", "LOSS", "DRAW", "OPEN", "VOID"})
            or record.outcome_source != "MANUAL_STUDY"
        ):
            raise ValueError("stored decision failed domain validation")
        return record

    def save(self, context: TenantContext, record: DecisionRecord) -> None:
        trusted = self._context(context)
        if not isinstance(record, DecisionRecord):
            raise TypeError("DecisionRecord is required")
        if record.execution_allowed:
            raise ValueError("decision memory cannot store execution authority")
        self.storage.put(
            trusted, self._RECORD_PREFIX + record.decision_id, record.to_dict()
        )
        self.storage.append_unique_list_item(
            trusted,
            self._INDEX_KEY,
            {"decision_id": record.decision_id},
            unique_field="decision_id",
            limit=2000,
        )

    def load(self, context: TenantContext, *, limit: int = 1000) -> list[DecisionRecord]:
        trusted = self._context(context)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise ValueError("limit must be an integer between 1 and 2000")
        index = self.storage.get(trusted, self._INDEX_KEY)
        if index is None:
            return []
        if not isinstance(index, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("decision_id"), str)
            or not item["decision_id"].strip()
            for item in index
        ):
            raise ValueError("stored decision index has an invalid shape")
        records: list[DecisionRecord] = []
        for item in index[-limit:]:
            raw = self.storage.get(
                trusted, self._RECORD_PREFIX + item["decision_id"]
            )
            if raw is None:
                raise ValueError("decision index references a missing record")
            record = self._record(raw)
            if record.decision_id != item["decision_id"]:
                raise ValueError("decision index and record identifiers do not match")
            records.append(record)
        return records

    def record_outcome(
        self, context: TenantContext, decision_id: str, outcome: str
    ) -> DecisionRecord:
        trusted = self._context(context)
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id is required")
        raw = self.storage.get(trusted, self._RECORD_PREFIX + decision_id.strip())
        if raw is None:
            raise ValueError("decision_id não encontrado")
        updated = self._record(raw).with_outcome(outcome, source="MANUAL_STUDY")
        self.storage.put(trusted, self._RECORD_PREFIX + updated.decision_id, updated.to_dict())
        return updated

    def readiness(self) -> dict[str, object]:
        return {
            "status": "LOCAL_TENANT_SCOPED_DECISION_MEMORY",
            "tenant_context_required": True,
            "legacy_global_history_migrated": False,
            "production_durable": self.storage.ready_for_production,
            "production_ready": False,
            "execution_authorized": False,
        }
