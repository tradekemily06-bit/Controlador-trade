from datetime import datetime, timedelta

from analysis.analyzer import TechnicalAnalyzer
from analysis.pressure import pressure_score
from analysis.rejection import rejection_score
from analysis.structure import structure_score
from analysis.trend import trend_score
from analysis.volume import volume_score
from data.models import Candle


BASE = datetime(2026, 1, 1, 10, 0, 0)


def candle(offset, open_, high, low, close, volume=1000):
    return Candle(
        timestamp=BASE + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_trend_alta():
    candles = [
        candle(0, 100, 105, 95, 102),
        candle(1, 102, 108, 100, 106),
        candle(2, 106, 112, 104, 110),
    ]
    assert trend_score(candles) == 100.0


def test_trend_baixa():
    candles = [
        candle(0, 110, 112, 104, 106),
        candle(1, 106, 108, 100, 102),
        candle(2, 102, 104, 96, 98),
    ]
    assert trend_score(candles) == 0.0


def test_pressao_compradora():
    assert pressure_score(candle(0, 100, 110, 99, 109)) > 50


def test_pressao_vendedora():
    assert pressure_score(candle(0, 109, 110, 99, 100)) < 50


def test_estrutura_alta():
    candles = [
        candle(0, 100, 105, 95, 102),
        candle(1, 102, 110, 100, 108),
    ]
    assert structure_score(candles) == 100.0


def test_rejeicao_inferior():
    assert rejection_score(candle(0, 105, 106, 95, 104)) > 50


def test_rejeicao_superior():
    assert rejection_score(candle(0, 100, 110, 99, 101)) < 50


def test_volume_alto_comprador():
    candles = [
        candle(0, 100, 105, 95, 102, 1000),
        candle(1, 102, 108, 100, 107, 1500),
    ]
    assert volume_score(candles) > 50


def test_analisador_completo():
    candles = [
        candle(0, 100, 105, 95, 102, 1000),
        candle(5, 102, 108, 100, 106, 1000),
        candle(10, 106, 112, 104, 110, 1500),
    ]

    result = TechnicalAnalyzer().analyze(candles, confirmed=True)

    assert result.trend == 100.0
    assert result.confirmation == 100.0
    assert 0 <= result.pressure <= 100
    assert 0 <= result.structure <= 100
    assert 0 <= result.rejection <= 100
    assert 0 <= result.volume <= 100
