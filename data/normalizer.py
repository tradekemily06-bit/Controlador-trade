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

    candle = Candle(
        timestamp=timestamp,
        open=float(open),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume),
    )

    if not candle.is_valid():
        raise ValueError("Dados de candle inválidos.")

    return candle
