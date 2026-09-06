from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """Representa um candle normalizado de mercado."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def is_valid(self) -> bool:
        """Verifica a consistência básica do candle."""
        if self.open < 0 or self.high < 0 or self.low < 0 or self.close < 0:
            return False

        if self.high < self.low:
            return False

        if self.high < max(self.open, self.close):
            return False

        if self.low > min(self.open, self.close):
            return False

        if self.volume < 0:
            return False

        return True
