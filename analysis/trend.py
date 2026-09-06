from data.models import Candle


def trend_score(candles: list[Candle]) -> float:
    """Estima direção pela evolução dos fechamentos e máximas/mínimas."""
    if len(candles) < 3:
        return 50.0

    recent = candles[-3:]

    rising_closes = recent[0].close < recent[1].close < recent[2].close
    falling_closes = recent[0].close > recent[1].close > recent[2].close

    rising_structure = (
        recent[0].high <= recent[1].high <= recent[2].high
        and recent[0].low <= recent[1].low <= recent[2].low
    )

    falling_structure = (
        recent[0].high >= recent[1].high >= recent[2].high
        and recent[0].low >= recent[1].low >= recent[2].low
    )

    if rising_closes and rising_structure:
        return 100.0

    if falling_closes and falling_structure:
        return 0.0

    if recent[-1].close > recent[0].close:
        return 65.0

    if recent[-1].close < recent[0].close:
        return 35.0

    return 50.0
