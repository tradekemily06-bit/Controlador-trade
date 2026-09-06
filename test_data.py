from datetime import datetime, timezone

import pytest

from data.models import Candle
from data.normalizer import normalize_candle


def test_candle_valido():
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=100,
        high=110,
        low=95,
        close=105,
        volume=1000,
    )

    assert candle.is_valid()


def test_candle_invalido_quando_high_menor_que_low():
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=100,
        high=90,
        low=95,
        close=100,
    )

    assert not candle.is_valid()


def test_normalizacao_converte_valores():
    candle = normalize_candle(
        timestamp=datetime.now(timezone.utc),
        open="100",
        high="110",
        low="95",
        close="105",
        volume="1000",
    )

    assert candle.open == 100.0
    assert candle.high == 110.0
    assert candle.low == 95.0
    assert candle.close == 105.0
    assert candle.volume == 1000.0


def test_normalizacao_rejeita_candle_invalido():
    with pytest.raises(ValueError):
        normalize_candle(
            timestamp=datetime.now(timezone.utc),
            open=100,
            high=90,
            low=95,
            close=100,
        )


def test_sequencia_de_candles_valida():
    from datetime import timedelta

    from data.validator import validate_candles

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base, 100, 105, 99, 103, 1000),
        Candle(base + timedelta(minutes=5), 103, 108, 102, 107, 1200),
        Candle(base + timedelta(minutes=10), 107, 110, 106, 109, 1300),
    ]

    assert validate_candles(
        candles,
        expected_interval=timedelta(minutes=5),
    )


def test_rejeita_candles_fora_de_ordem():
    from datetime import timedelta

    from data.validator import validate_candles

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base + timedelta(minutes=5), 103, 108, 102, 107),
        Candle(base, 100, 105, 99, 103),
    ]

    assert not validate_candles(candles)


def test_rejeita_timestamp_duplicado():
    from data.validator import validate_candles

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base, 100, 105, 99, 103),
        Candle(base, 100, 106, 98, 104),
    ]

    assert not validate_candles(candles)


def test_rejeita_gap_no_intervalo():
    from datetime import timedelta

    from data.validator import validate_candles

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base, 100, 105, 99, 103),
        Candle(base + timedelta(minutes=5), 103, 108, 102, 107),
        Candle(base + timedelta(minutes=15), 107, 110, 106, 109),
    ]

    assert not validate_candles(
        candles,
        expected_interval=timedelta(minutes=5),
    )


def test_rejeita_valor_infinito():
    from data.validator import validate_candles

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base, float("inf"), 105, 99, 103),
    ]

    assert not validate_candles(candles)


def test_timeframe_5m():
    from datetime import timedelta

    from data.timeframes import get_timeframe_interval

    assert get_timeframe_interval("5m") == timedelta(minutes=5)


def test_timeframe_invalido():
    from data.timeframes import get_timeframe_interval

    with pytest.raises(ValueError):
        get_timeframe_interval("99m")


def test_cria_serie_de_candles():
    from datetime import timedelta

    from data.series import CandleSeries

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base, 100, 105, 99, 103),
        Candle(base + timedelta(minutes=5), 103, 108, 102, 107),
        Candle(base + timedelta(minutes=10), 107, 110, 106, 109),
    ]

    series = CandleSeries.create(candles, "5m")

    assert len(series) == 3
    assert series.timeframe == "5m"
    assert series.last.close == 109


def test_serie_rejeita_candles_invalidos():
    from data.series import CandleSeries

    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    candles = [
        Candle(base, 100, 90, 95, 100),
    ]

    with pytest.raises(ValueError):
        CandleSeries.create(candles, "5m")
