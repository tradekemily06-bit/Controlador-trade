from datetime import timedelta
from math import isfinite

from .models import Candle


def validate_candles(
    candles: list[Candle],
    *,
    expected_interval: timedelta | None = None,
) -> bool:
    """Valida integridade básica e ordem de uma sequência de candles."""

    if not candles:
        return False

    for candle in candles:
        if not isinstance(candle, Candle):
            return False

        values = (
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
        )

        if not all(isfinite(value) for value in values):
            return False

        if not candle.is_valid():
            return False

    timestamps = [candle.timestamp for candle in candles]

    # Candles precisam estar em ordem cronológica e não podem se repetir.
    if timestamps != sorted(timestamps):
        return False

    if len(set(timestamps)) != len(timestamps):
        return False

    # Quando o intervalo esperado é conhecido, todos os candles
    # devem respeitar exatamente esse espaçamento.
    if expected_interval is not None:
        if expected_interval <= timedelta(0):
            return False

        for previous, current in zip(timestamps, timestamps[1:]):
            if current - previous != expected_interval:
                return False

    return True
