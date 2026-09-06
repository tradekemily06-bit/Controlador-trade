from data.models import Candle


def rejection_score(candle: Candle) -> float:
    """Avalia rejeição por pavios em relação ao range do candle."""
    candle_range = candle.high - candle.low

    if candle_range <= 0:
        return 50.0

    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low

    upper_ratio = upper_wick / candle_range
    lower_ratio = lower_wick / candle_range

    if lower_ratio > upper_ratio and lower_ratio >= 0.35:
        return 75.0

    if upper_ratio > lower_ratio and upper_ratio >= 0.35:
        return 25.0

    return 50.0
