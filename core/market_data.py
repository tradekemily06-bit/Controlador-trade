from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """Representa um candle OHLCV de mercado."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp deve ser um datetime.")

        values = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

        for name, value in values.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"{name} deve ser numérico.")

        if self.open <= 0:
            raise ValueError("open deve ser maior que zero.")

        if self.high <= 0:
            raise ValueError("high deve ser maior que zero.")

        if self.low <= 0:
            raise ValueError("low deve ser maior que zero.")

        if self.close <= 0:
            raise ValueError("close deve ser maior que zero.")

        if self.volume < 0:
            raise ValueError("volume não pode ser negativo.")

        if self.high < self.low:
            raise ValueError("high não pode ser menor que low.")

        if not self.low <= self.open <= self.high:
            raise ValueError("open deve estar entre low e high.")

        if not self.low <= self.close <= self.high:
            raise ValueError("close deve estar entre low e high.")
