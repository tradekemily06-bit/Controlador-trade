from __future__ import annotations

import hashlib
from collections.abc import Iterable

from data.models import Candle


def fingerprint_candles(candles: Iterable[Candle]) -> str:
    """Return a deterministic identity for the exact normalized candle sequence."""
    digest = hashlib.sha256()
    for candle in candles:
        if not isinstance(candle, Candle):
            raise TypeError("candles deve conter somente Candle")
        timestamp = candle.timestamp.isoformat()
        digest.update(
            f"{timestamp}|{candle.open!r}|{candle.high!r}|{candle.low!r}|"
            f"{candle.close!r}|{candle.volume!r}\n".encode("utf-8")
        )
    return digest.hexdigest()
