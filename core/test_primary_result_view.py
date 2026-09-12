from core.models import AnalysisResult, Signal
from core.primary_result_view import build_primary_result_view


def test_primary_result_is_the_signal_and_real_is_separate_security_state():
    result = AnalysisResult(
        signal=Signal.COMPRA,
        score=91,
        reason="confirmação",
        confirmed=True,
        symbol="BTCUSD",
        timeframe="5m",
    )

    view = build_primary_result_view(result)

    assert view.primary.label == "COMPRA"
    assert view.primary.color == "green"
    assert view.primary.priority == 100
    assert view.real_security.label == "REAL BLOQUEADO"
    assert view.real_security.discreet is True
    assert view.real_security.status.value == "REAL_BLOCKED"


def test_wait_remains_primary_when_signal_is_await():
    result = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=55,
        reason="sem confirmação",
    )
    view = build_primary_result_view(result)
    assert view.primary.label == "AGUARDAR"
    assert view.primary.color == "yellow"


def test_invalid_result_is_rejected():
    try:
        build_primary_result_view(object())
    except TypeError:
        pass
    else:
        raise AssertionError("invalid result must be rejected")
