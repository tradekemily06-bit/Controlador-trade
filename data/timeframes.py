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


def list_supported_timeframes(*, platform_format: bool = False) -> tuple[str, ...]:
    """List supported fixed-duration intervals in canonical or platform form.

    Calendar months and seconds are intentionally excluded: they require
    calendar-aware boundaries or sub-minute source data, respectively.
    """
    if not isinstance(platform_format, bool):
        raise ValueError("platform_format must be boolean")
    suffixes = {"m": "M", "h": "H", "d": "D", "w": "W"}
    limits = {"m": 59, "h": 24, "d": 31, "w": 4}
    values = []
    for unit, maximum in limits.items():
        for count in range(1, maximum + 1):
            values.append(f"{suffixes[unit]}{count}" if platform_format else f"{count}{unit}")
    return tuple(values)

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
