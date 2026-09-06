from data.models import Candle


def volume_score(candles: list[Candle]) -> float:
    """Compara o volume do último candle com a média anterior."""
    if len(candles) < 2:
        return 50.0

    previous = candles[:-1]
    last = candles[-1]

    average = sum(c.volume for c in previous) / len(previous)

    if average <= 0:
        return 50.0

    if last.volume > average * 1.2:
        if last.close > last.open:
            return 70.0
        if last.close < last.open:
            return 30.0

    return 50.0
