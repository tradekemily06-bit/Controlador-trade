from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Optional


class OperationalStateValidationError(ValueError):
    """Raised when operational state contains invalid data."""


def _finite_number(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OperationalStateValidationError(
            f"{name} must be a finite number"
        )
    if not math.isfinite(float(value)):
        raise OperationalStateValidationError(
            f"{name} must be finite"
        )


def _counter(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OperationalStateValidationError(
            f"{name} must be a non-negative integer"
        )


@dataclass(frozen=True)
class OperationalState:
    """
    Immutable snapshot of the operational state required for risk decisions.

    None means UNKNOWN, not zero and never implicit approval.
    """

    balance: Optional[float] = None
    equity: Optional[float] = None
    realized_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None

    trades_today: Optional[int] = None
    consecutive_losses: Optional[int] = None
    open_positions: Optional[int] = None

    net_position: Optional[float] = None
    exposure: Optional[float] = None

    market_open: Optional[bool] = None
    last_processed_candle: Optional[datetime] = None

    def __post_init__(self) -> None:
        for name in (
            "balance",
            "equity",
            "realized_pnl",
            "unrealized_pnl",
            "net_position",
            "exposure",
        ):
            value = getattr(self, name)
            if value is not None:
                _finite_number(value, name)

        for name in (
            "trades_today",
            "consecutive_losses",
            "open_positions",
        ):
            value = getattr(self, name)
            if value is not None:
                _counter(value, name)

        if self.market_open is not None and not isinstance(
            self.market_open, bool
        ):
            raise OperationalStateValidationError(
                "market_open must be bool or None"
            )

        if self.last_processed_candle is not None and not isinstance(
            self.last_processed_candle, datetime
        ):
            raise OperationalStateValidationError(
                "last_processed_candle must be datetime or None"
            )

    def risk_fields_available(self) -> bool:
        """
        Required information for the current risk policies.

        Unknown values remain unknown and therefore cannot approve risk.
        """
        return (
            self.trades_today is not None
            and self.consecutive_losses is not None
        )
