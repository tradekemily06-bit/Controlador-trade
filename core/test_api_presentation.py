from core.api_presentation import (
    PresentationStatus,
    presentation_for_signal,
    real_blocked_token,
)
from core.models import Signal


def test_primary_signal_colors_are_unambiguous():
    assert presentation_for_signal(Signal.COMPRA).color == "green"
    assert presentation_for_signal(Signal.VENDA).color == "red"
    assert presentation_for_signal(Signal.AGUARDAR).color == "yellow"


def test_secondary_semantics_are_distinct():
    from core.api_presentation import TOKENS

    assert TOKENS[PresentationStatus.ANALYSIS].color == "blue"
    assert TOKENS[PresentationStatus.RISK].color == "orange"
    assert TOKENS[PresentationStatus.NEUTRAL].color == "gray"


def test_real_is_blocked_and_discreet():
    token = real_blocked_token()
    assert token.status is PresentationStatus.REAL_BLOCKED
    assert token.discreet is True
    assert token.label == "REAL BLOQUEADO"
