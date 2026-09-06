from datetime import timedelta


TIMEFRAMES = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def get_timeframe_interval(timeframe: str) -> timedelta:
    """Retorna o intervalo correspondente ao timeframe informado."""

    try:
        return TIMEFRAMES[timeframe]
    except KeyError as exc:
        raise ValueError(f"Timeframe não suportado: {timeframe}") from exc
