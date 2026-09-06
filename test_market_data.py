from datetime import datetime

import pytest

from core.market_data import Candle


def candle_valido():
    return Candle(
        timestamp=datetime(2026, 9, 6, 10, 0),
        open=100,
        high=110,
        low=95,
        close=108,
        volume=1000,
    )


def test_candle_valido():
    candle = candle_valido()

    assert candle.open == 100
    assert candle.high == 110
    assert candle.low == 95
    assert candle.close == 108
    assert candle.volume == 1000


def test_candle_e_imutavel():
    candle = candle_valido()

    with pytest.raises(AttributeError):
        candle.close = 120


@pytest.mark.parametrize(
    "field",
    ["open", "high", "low", "close"],
)
def test_preco_deve_ser_maior_que_zero(field):
    values = {
        "timestamp": datetime(2026, 9, 6, 10, 0),
        "open": 100,
        "high": 110,
        "low": 95,
        "close": 108,
        "volume": 1000,
    }

    values[field] = 0

    with pytest.raises(ValueError):
        Candle(**values)


def test_volume_nao_pode_ser_negativo():
    values = {
        "timestamp": datetime(2026, 9, 6, 10, 0),
        "open": 100,
        "high": 110,
        "low": 95,
        "close": 108,
        "volume": -1,
    }

    with pytest.raises(ValueError):
        Candle(**values)


def test_high_nao_pode_ser_menor_que_low():
    with pytest.raises(ValueError):
        Candle(
            timestamp=datetime(2026, 9, 6, 10, 0),
            open=100,
            high=90,
            low=95,
            close=98,
            volume=1000,
        )


def test_open_deve_estar_entre_low_e_high():
    with pytest.raises(ValueError):
        Candle(
            timestamp=datetime(2026, 9, 6, 10, 0),
            open=120,
            high=110,
            low=95,
            close=108,
            volume=1000,
        )


def test_close_deve_estar_entre_low_e_high():
    with pytest.raises(ValueError):
        Candle(
            timestamp=datetime(2026, 9, 6, 10, 0),
            open=100,
            high=110,
            low=95,
            close=120,
            volume=1000,
        )


def test_timestamp_deve_ser_datetime():
    with pytest.raises(ValueError):
        Candle(
            timestamp="2026-09-06T10:00:00",
            open=100,
            high=110,
            low=95,
            close=108,
            volume=1000,
        )
