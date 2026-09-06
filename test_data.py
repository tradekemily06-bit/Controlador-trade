from datetime import datetime, timedelta

import pytest

from data.models import Candle
from data.normalizer import normalize_candle
from data.series import CandleSeries
from data.timeframes import get_timeframe_interval
from data.validator import validate_candles


BASE = datetime(2026, 1, 1, 10, 0, 0)


def make_candle(offset=0, **overrides):
    values = {
        "timestamp": BASE + timedelta(minutes=offset),
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0,
    }
    values.update(overrides)
    return Candle(**values)


def test_candle_valido():
    assert make_candle().is_valid()


def test_rejeita_ohlc_inconsistente():
    assert not make_candle(high=90.0).is_valid()


def test_rejeita_volume_negativo():
    assert not make_candle(volume=-1.0).is_valid()


def test_normaliza_candle():
    candle = normalize_candle(
        timestamp=BASE,
        open="100",
        high="105",
        low="95",
        close="102",
        volume="1000",
    )
    assert candle.open == 100.0
    assert candle.volume == 1000.0


def test_normalizer_rejeita_candle_invalido():
    with pytest.raises(ValueError):
        normalize_candle(
            timestamp=BASE,
            open=100,
            high=90,
            low=95,
            close=102,
        )


def test_rejeita_nan():
    assert not make_candle(open=float("nan")).is_valid()


def test_rejeita_infinito():
    assert not make_candle(close=float("inf")).is_valid()


def test_normalizer_rejeita_timestamp_invalido():
    with pytest.raises(ValueError):
        normalize_candle(
            timestamp="2026-01-01T10:00:00",
            open=100,
            high=105,
            low=95,
            close=102,
        )


def test_validate_candles_validos():
    candles = [make_candle(0), make_candle(1), make_candle(2)]
    assert validate_candles(candles)


def test_rejeita_candles_fora_de_ordem():
    candles = [make_candle(1), make_candle(0)]
    assert not validate_candles(candles)


def test_rejeita_timestamps_duplicados():
    candles = [make_candle(0), make_candle(0)]
    assert not validate_candles(candles)


def test_rejeita_intervalo_incorreto():
    candles = [make_candle(0), make_candle(2)]
    assert not validate_candles(
        candles,
        expected_interval=timedelta(minutes=1),
    )


def test_timeframe_e_series():
    assert get_timeframe_interval("5m") == timedelta(minutes=5)

    candles = [
        make_candle(0),
        make_candle(5),
        make_candle(10),
    ]

    series = CandleSeries.create(candles, "5m")

    assert len(series) == 3
    assert series.last == candles[-1]
