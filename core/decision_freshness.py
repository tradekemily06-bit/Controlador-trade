from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class DecisionFreshnessPolicy:
    """Fail-closed freshness policy for decisions crossing into execution."""

    max_age_seconds: float = 30.0
    max_future_skew_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds deve ser positivo.")
        if self.max_future_skew_seconds < 0:
            raise ValueError("max_future_skew_seconds não pode ser negativo.")

    def validate(self, created_at: datetime, *, now: datetime) -> str | None:
        if not isinstance(created_at, datetime) or not isinstance(now, datetime):
            return "timestamp de decisão inválido"
        if created_at.tzinfo is None or now.tzinfo is None:
            return "timestamp de decisão sem timezone"
        created_utc = created_at.astimezone(timezone.utc)
        now_utc = now.astimezone(timezone.utc)
        future_limit = now_utc + timedelta(seconds=self.max_future_skew_seconds)
        if created_utc > future_limit:
            return "decisão rejeitada: timestamp está no futuro"
        age = (now_utc - created_utc).total_seconds()
        if age > self.max_age_seconds:
            return (
                "decisão expirada: a avaliação ficou velha demais para execução; "
                "nova análise obrigatória"
            )
        return None
