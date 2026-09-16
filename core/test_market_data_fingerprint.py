from datetime import datetime, timezone

import pytest

from core.market_data_fingerprint import fingerprint_candles
from data.models import Candle


def candles(close: float = 100.0):
    return (
        Candle(datetime(2026, 1, 1, tzinfo=timezone.utc), 99, 101, 98, close, 10),
        Candle(datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc), close, 102, 99, close + 1, 11),
    )


def test_same_normalized_candles_have_same_fingerprint():
    assert fingerprint_candles(candles()) == fingerprint_candles(tuple(candles()))


def test_changed_candle_has_different_fingerprint():
    assert fingerprint_candles(candles()) != fingerprint_candles(candles(101.0))


def test_fingerprint_rejects_non_candle_values():
    with pytest.raises(TypeError):
        fingerprint_candles([object()])
