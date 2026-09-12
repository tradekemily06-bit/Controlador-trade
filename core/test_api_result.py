from core.api_result import serialize_primary_result
from core.models import AnalysisResult, Signal


def test_serialize_primary_result_exposes_buy_and_real_safety_state():
    result = AnalysisResult(
        signal=Signal.COMPRA,
        score=91,
        reason="confirmação",
        confirmed=True,
        symbol="BTCUSD",
        timeframe="5m",
    )

    payload = serialize_primary_result(result)

    assert payload["signal"] == "COMPRA"
    assert payload["score"] == 91
    assert payload["presentation"] == {
        "status": "BUY",
        "label": "COMPRA",
        "color": "green",
        "priority": 100,
    }
    assert payload["security"]["real_blocked"] is True
    assert payload["security"]["discreet"] is True


def test_serialize_primary_result_keeps_wait_as_primary_result():
    result = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=55,
        reason="sem confirmação",
    )

    payload = serialize_primary_result(result)

    assert payload["presentation"]["label"] == "AGUARDAR"
    assert payload["presentation"]["color"] == "yellow"
    assert payload["security"]["real_blocked"] is True
