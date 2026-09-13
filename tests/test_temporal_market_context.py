from core.temporal_market_context import TemporalMarketContextEngine
from data.models import Candle


def candle(open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(open=open_, high=high, low=low, close=close)


def test_history_present_and_future_are_kept_separate():
    result = TemporalMarketContextEngine().analyze([
        candle(100, 102, 99, 101),
        candle(101, 104, 100, 103),
        candle(103, 106, 102, 105),
    ])

    assert result.historical
    assert result.present
    assert result.scenarios
    assert all(item.phase.value == "HISTORICAL" for item in result.historical)
    assert all(item.phase.value == "PRESENT" for item in result.present)
    assert all(item.condition for item in result.scenarios)


def test_future_is_conditional_not_claimed_as_prediction():
    result = TemporalMarketContextEngine().analyze([
        candle(100, 101, 99, 100.5),
        candle(100.5, 103, 100, 102.5),
    ])

    assert result.scenarios
    assert all("Se " in scenario.condition for scenario in result.scenarios)
    assert "não é observado" in result.uncertainty[0]


def test_insufficient_history_does_not_invent_context():
    result = TemporalMarketContextEngine().analyze([])

    assert result.historical == ()
    assert result.present == ()
    assert result.scenarios == ()
    assert result.uncertainty
