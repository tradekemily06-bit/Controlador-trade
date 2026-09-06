from datetime import datetime

from .models import Candle


def normalize_candle(
    *,
    timestamp,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
) -> Candle:
    """Cria um candle padronizado e rejeita dados inválidos."""

    if not isinstance(timestamp, datetime):
        raise ValueError("Timestamp inválido.")

    try:
        candle = Candle(
            timestamp=timestamp,
            open=float(open),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Dados de candle inválidos.") from exc

    if not candle.is_valid():
        raise ValueError("Dados de candle inválidos.")

    return candle
