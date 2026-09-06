from data.models import Candle


def structure_score(candles: list[Candle]) -> float:
    """Avalia estrutura simples de topos e fundos recentes."""
    if len(candles) < 2:
        return 50.0

    previous = candles[-2]
    current = candles[-1]

    higher_high = current.high > previous.high
    higher_low = current.low > previous.low

    lower_high = current.high < previous.high
    lower_low = current.low < previous.low

    if higher_high and higher_low:
        return 100.0

    if lower_high and lower_low:
        return 0.0

    if current.close > previous.close:
        return 65.0

    if current.close < previous.close:
        return 35.0

    return 50.0
