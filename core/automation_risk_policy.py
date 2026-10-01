from __future__ import annotations

import math
import os
from dataclasses import dataclass

from core.p39_pretrade_risk import RiskLimits


@dataclass(frozen=True)
class AutomationRiskPolicy:
    """Explicit execution-risk configuration; missing limits never approve."""

    max_order_volume: float | None = None
    max_total_volume: float | None = None

    @property
    def configured(self) -> bool:
        return self.max_order_volume is not None and self.max_total_volume is not None

    def limits(self) -> RiskLimits | None:
        if not self.configured:
            return None
        return RiskLimits(
            max_order_amount=float(self.max_order_volume),
            max_total_exposure=float(self.max_total_volume),
        )

    @classmethod
    def from_environment(cls) -> "AutomationRiskPolicy":
        return cls(
            max_order_volume=cls._read_positive("CONTROLADOR_RISK_MAX_ORDER_VOLUME"),
            max_total_volume=cls._read_positive("CONTROLADOR_RISK_MAX_TOTAL_VOLUME"),
        )

    @staticmethod
    def _read_positive(name: str) -> float | None:
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value <= 0:
            return None
        return value
