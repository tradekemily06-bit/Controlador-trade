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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_outcome(self, outcome: str) -> "DecisionRecord":
        if outcome not in {"WIN", "LOSS", "DRAW", "OPEN", "VOID"}:
            raise ValueError("outcome inválido")
        return DecisionRecord(**{**self.to_dict(), "outcome": outcome})

    @property
    def is_actionable(self) -> bool:
        return self.confirmed and self.signal in {Signal.COMPRA.value, Signal.VENDA.value}
