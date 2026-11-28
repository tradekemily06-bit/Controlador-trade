"""Explicit transaction-cost accounting for research-only trade returns.

All monetary inputs must already be converted to the same account currency.
Unknown costs are rejected: they are never silently treated as zero.
This module does not infer broker fees or authorize trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Mapping


_COST_FIELDS = ("spread", "commission", "slippage", "swap", "financing", "conversion")


@dataclass(frozen=True)
class TradeCostBreakdown:
    """Auditable cost amounts, in one account currency, for one completed trade."""

    spread: float
    commission: float
    slippage: float
    swap: float
    financing: float
    conversion: float
    currency: str
    source_id: str
    verified_at: str

    def validated_amounts(self) -> dict[str, float]:
        currency = self.currency
        if not isinstance(currency, str) or not currency.strip() or len(currency.strip()) > 12:
            raise ValueError("currency must be a non-empty account-currency code")
        if not isinstance(self.source_id, str) or not self.source_id.strip() or len(self.source_id) > 160:
            raise ValueError("source_id is required for cost provenance")
        if not isinstance(self.verified_at, str):
            raise ValueError("verified_at is required for cost provenance")
        try:
            timestamp = datetime.fromisoformat(self.verified_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("verified_at must be ISO-8601 text") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("verified_at must include a timezone")
        amounts: dict[str, float] = {}
        for field in _COST_FIELDS:
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field} cost is missing or not numeric; unknown costs cannot be zero-filled")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0:
                raise ValueError(f"{field} cost must be finite and non-negative")
            amounts[field] = numeric
        return amounts


def calculate_net_trade_return(
    *,
    gross_profit_loss: float,
    capital_at_risk: float,
    costs: TradeCostBreakdown,
) -> dict[str, object]:
    """Return net P/L and return only when every cost component is explicitly supplied."""
    if isinstance(gross_profit_loss, bool) or not isinstance(gross_profit_loss, (int, float)):
        raise ValueError("gross_profit_loss must be numeric")
    gross = float(gross_profit_loss)
    if not math.isfinite(gross):
        raise ValueError("gross_profit_loss must be finite")
    if isinstance(capital_at_risk, bool) or not isinstance(capital_at_risk, (int, float)):
        raise ValueError("capital_at_risk must be numeric")
    capital = float(capital_at_risk)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("capital_at_risk must be finite and positive")
    amounts = costs.validated_amounts()
    total_cost = sum(amounts.values())
    net = gross - total_cost
    result: dict[str, object] = {
        "gross_profit_loss": gross,
        "costs": amounts,
        "total_cost": total_cost,
        "net_profit_loss": net,
        "capital_at_risk": capital,
        "net_return": net / capital,
        "currency": costs.currency.strip().upper(),
        "cost_provenance": {
            "source_id": costs.source_id.strip(),
            "verified_at": datetime.fromisoformat(costs.verified_at.replace("Z", "+00:00")).isoformat(),
            "components_complete": True,
            "unknown_costs_defaulted_to_zero": False,
        },
        "research_only": True,
        "execution_authorized": False,
    }
    return result
