from data.models import Candle


def pressure_score(candle: Candle) -> float:
    """Estima pressão pelo corpo do candle e sua posição no range."""
    candle_range = candle.high - candle.low

    if candle_range <= 0:
        return 50.0

    body = candle.close - candle.open
    body_ratio = abs(body) / candle_range

    if body > 0:
        return min(100.0, 50.0 + body_ratio * 50.0)

    if body < 0:
        return max(0.0, 50.0 - body_ratio * 50.0)

    return 50.0
