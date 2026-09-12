from core.api_result import serialize_primary_result
from core.models import AnalysisResult, Signal


def test_serialize_primary_result_exposes_buy_presentation_and_real_safety():
    result = AnalysisResult(
        signal=Signal.COMPRA,
        score=82.5,
        reason="confirmed bullish analysis",
        confirmed=True,
        symbol="BTCUSD",
        timeframe="5m",
    )

    payload = serialize_primary_result(result)

    assert payload["signal"] == "COMPRA"
    assert payload["score"] == 82.5
    assert payload["presentation"] == {
        "status": "BUY",
        "label": "COMPRA",
        "color": "green",
        "priority": 100,
    }
    assert payload["security"]["real_blocked"] is True
    assert payload["security"]["discreet"] is True


def test_serialize_primary_result_preserves_wait_state():
    result = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=55,
        reason="waiting for confirmation",
        confirmed=False,
        symbol="EURUSD",
        timeframe="5m",
    )

    payload = serialize_primary_result(result)

    assert payload["signal"] == "AGUARDAR"
    assert payload["presentation"]["status"] == "WAIT"
    assert payload["presentation"]["color"] == "yellow"
    assert payload["security"]["real_blocked"] is True
