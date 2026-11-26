from __future__ import annotations

import re
from datetime import timedelta


# Common intervals remain discoverable for UI defaults and legacy callers.
TIMEFRAMES = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "10m": timedelta(minutes=10),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

_TIMEFRAME_PATTERN = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>m|h|d|w)$", re.IGNORECASE)
_PLATFORM_PATTERN = re.compile(r"^(?P<unit>M|H|D|W)(?P<count>[1-9][0-9]*)$", re.IGNORECASE)


def normalize_timeframe(timeframe: str) -> str:
    """Normalize common platform forms (M1/H1/D1/W1) and compact forms (1m/1h)."""
    if not isinstance(timeframe, str):
        raise ValueError("Timeframe deve ser texto")
    value = timeframe.strip()
    match = _PLATFORM_PATTERN.fullmatch(value)
    if match:
        value = f"{match.group('count')}{match.group('unit').lower()}"
    match = _TIMEFRAME_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Timeframe não suportado: {timeframe}")
    count = int(match.group("count"))
    unit = match.group("unit").lower()
    limits = {"m": 59, "h": 24, "d": 31, "w": 4}
    if count > limits[unit]:
        raise ValueError(f"Timeframe fora do limite suportado: {timeframe}")
    return f"{count}{unit}"


def get_timeframe_interval(timeframe: str) -> timedelta:
    """Return the interval for supported minute, hour, day or week periods."""
    value = normalize_timeframe(timeframe)
    count = int(value[:-1])
    unit = value[-1]
    factors = {
        "m": timedelta(minutes=1),
        "h": timedelta(hours=1),
        "d": timedelta(days=1),
        "w": timedelta(weeks=1),
    }
    return factors[unit] * count
