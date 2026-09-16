from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.models import AnalysisResult, Signal


@dataclass(frozen=True)
class DecisionRecord:
    """Immutable explanation of one analysis decision.

    This is a learning/audit record only. It never submits an order.
    ``subject_id`` and ``tenant_id`` are ownership metadata supplied by a
    trusted application boundary; they must never be taken as proof merely
    because a browser supplied them.
    """

    decision_id: str
    created_at: str
    symbol: str | None
    timeframe: str | None
    signal: str
    score: float
    confirmed: bool
    reason: str
    execution_allowed: bool = False
    outcome: str | None = None
    subject_id: str | None = None
    tenant_id: str | None = None

    @classmethod
    def from_analysis(cls, result: AnalysisResult) -> "DecisionRecord":
        return cls(
            decision_id=str(uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol=result.symbol,
            timeframe=result.timeframe,
            signal=result.signal.value,
            score=float(result.score),
            confirmed=bool(result.confirmed),
            reason=result.reason,
        )

    def owned_by(self, *, subject_id: str, tenant_id: str) -> bool:
        return (
            isinstance(subject_id, str)
            and bool(subject_id.strip())
            and isinstance(tenant_id, str)
            and bool(tenant_id.strip())
            and self.subject_id == subject_id.strip()
            and self.tenant_id == tenant_id.strip()
        )

    def with_owner(self, *, subject_id: str, tenant_id: str) -> "DecisionRecord":
        if not isinstance(subject_id, str) or not subject_id.strip():
            raise ValueError("subject_id is required")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if self.subject_id is not None or self.tenant_id is not None:
            if not self.owned_by(subject_id=subject_id, tenant_id=tenant_id):
                raise ValueError("decision ownership cannot be reassigned")
            return self
        return DecisionRecord(**{
            **self.to_dict(),
            "subject_id": subject_id.strip(),
            "tenant_id": tenant_id.strip(),
        })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_outcome(self, outcome: str) -> "DecisionRecord":
        if outcome not in {"WIN", "LOSS", "DRAW", "OPEN", "VOID"}:
            raise ValueError("outcome inválido")
        return DecisionRecord(**{**self.to_dict(), "outcome": outcome})

    @property
    def is_actionable(self) -> bool:
        return self.confirmed and self.signal in {Signal.COMPRA.value, Signal.VENDA.value}
