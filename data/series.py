from dataclasses import dataclass

from .models import Candle
from .timeframes import get_timeframe_interval
from .validator import validate_candles


@dataclass(frozen=True)
class CandleSeries:
    """Representa uma sequência validada de candles."""

    candles: tuple[Candle, ...]
    timeframe: str

    @classmethod
    def create(cls, candles: list[Candle], timeframe: str):
        interval = get_timeframe_interval(timeframe)

        if not validate_candles(
            candles,
            expected_interval=interval,
        ):
            raise ValueError("Sequência de candles inválida.")

        return cls(
            candles=tuple(candles),
            timeframe=timeframe,
        )

    @property
    def last(self) -> Candle:
        """Retorna o candle mais recente da série."""
        return self.candles[-1]

    def __len__(self) -> int:
        return len(self.candles)
