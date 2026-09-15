from __future__ import annotations

from dataclasses import asdict
from typing import Any

from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods
from integration.production_data_plane import ProductionDataPlane
from security.http_identity import saas_public_mode


class ProductionScopedServiceMixin:
    """Replace process-global decision state with durable scoped state.

    Local/test mode keeps the existing DecisionStore behavior. Once a
    production data plane is configured, owned records are read and written
    through that provider. Public SaaS mode fails closed if no provider is
    configured instead of falling back to process memory.
    """

    def __init__(self, *args: Any, production_data_plane: ProductionDataPlane | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.production_data_plane = production_data_plane if production_data_plane is not None else ProductionDataPlane.from_config()
        if self.production_data_plane is not None:
            self.production_storage = self.production_data_plane.policy
            from security.production_operation_gate import ProductionOperationGate
            self.production_gate = ProductionOperationGate(self.production_storage)

    def _production_scope_required(self) -> bool:
        return bool(self.production_data_plane is not None or saas_public_mode())

    def _production_records(self, owner, *, limit: int | None = None) -> list[DecisionRecord]:
        if owner is None:
            if self._production_scope_required():
                raise PermissionError("trusted tenant and subject scope are required for production decision state")
            return list(self.memory)
        if self.production_data_plane is None:
            raise RuntimeError("production storage provider is required for owned decision state")
        return self.production_data_plane.list(
            tenant_id=owner.tenant_id,
            subject_id=owner.subject_id,
            limit=limit,
        )

    def _scoped_memory(self, owner):
        if self.production_data_plane is not None or saas_public_mode():
            return self._production_records(owner)
        return super()._scoped_memory(owner)

    def _persist_records(self, records: list[DecisionRecord]) -> None:
        if not records:
            return
        owned = [record for record in records if record.subject_id is not None or record.tenant_id is not None]
        unowned = [record for record in records if record.subject_id is None and record.tenant_id is None]

        if self.production_data_plane is not None:
            if unowned:
                raise PermissionError("production decision records require tenant and subject ownership")
            for record in owned:
                self.production_data_plane.save(
                    record,
                    tenant_id=record.tenant_id,
                    subject_id=record.subject_id,
                )
            return

        if saas_public_mode():
            raise RuntimeError("production storage provider is not configured; local decision fallback is disabled")

        super()._persist_records(records)

    def record_outcome(self, decision_id: str, outcome: str, *, subject_id: str | None = None, tenant_id: str | None = None) -> DecisionRecord:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        if self.production_data_plane is None and not saas_public_mode():
            return super().record_outcome(decision_id, outcome, subject_id=subject_id, tenant_id=tenant_id)
        if owner is None:
            raise PermissionError("trusted tenant and subject scope are required for production outcome updates")
        if self.production_data_plane is None:
            raise RuntimeError("production storage provider is not configured")
        record = self.production_data_plane.load(
            decision_id,
            tenant_id=owner.tenant_id,
            subject_id=owner.subject_id,
        )
        if record is None:
            raise ValueError("decision_id não encontrado")
        updated = record.with_outcome(outcome)
        self.production_data_plane.save(
            updated,
            tenant_id=owner.tenant_id,
            subject_id=owner.subject_id,
        )
        return updated

    def statistics(self, *, subject_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        if self.production_data_plane is None and not saas_public_mode():
            return super().statistics(subject_id=subject_id, tenant_id=tenant_id)
        # Statistics are aggregates over the complete scoped history. They must
        # never silently inherit a UI pagination limit.
        scoped = self._production_records(owner, limit=None)
        breakdowns = summarize_breakdowns(scoped)
        return {
            **asdict(summarize(scoped)),
            "periods": summarize_periods(scoped),
            "breakdowns": {
                **breakdowns,
                "by_symbol": breakdowns["symbols"],
                "by_timeframe": breakdowns["timeframes"],
                "by_signal": breakdowns["signals"],
                "by_score_band": breakdowns["score_bands"],
            },
        }

    def memory_view(self, limit: int = 50, *, subject_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        if self.production_data_plane is None and not saas_public_mode():
            return super().memory_view(limit=limit, subject_id=subject_id, tenant_id=tenant_id)
        # This limit is presentation pagination, not a cap on stored history.
        records = self._production_records(owner, limit=limit)
        return [item.to_dict() for item in records[:limit]]
