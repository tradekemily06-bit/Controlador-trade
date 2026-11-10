from __future__ import annotations

from streamlit_panel.presentation import closed_panel_signal


def test_closed_panel_signal_maps_supported_signal_names_and_strength_bands():
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": 69}}) == (
        "↑ COMPRAR", "69% · FRACA", "#46D6AD"
    )
    assert closed_panel_signal({"signal": "SELL", "analysis": {"score": 70}}) == (
        "↓ VENDER", "70% · MODERADA", "#FF667A"
    )
    assert closed_panel_signal({"signal": "WAIT", "analysis": {"score": 80}}) == (
        "AGUARDAR", "80% · FORTE", "#E8C66A"
    )
    assert closed_panel_signal({"signal": "COMPRAR", "analysis": {"score": 100}})[1] == (
        "100% · FORTE"
    )
    assert closed_panel_signal({"signal": "VENDER", "analysis": {"score": 1}})[1] == (
        "1% · FRACA"
    )
    assert closed_panel_signal({"signal": "AGUARDAR", "analysis": {"score": 79}})[1] == (
        "79% · MODERADA"
    )


def test_closed_panel_signal_fails_closed_for_missing_or_invalid_analysis():
    invalid_results = (
        None,
        [],
        {},
        {"signal": "BUY"},
        {"signal": "BUY", "analysis": None},
        {"signal": "BUY", "analysis": {"score": True}},
        {"signal": "BUY", "analysis": {"score": 0}},
        {"signal": "BUY", "analysis": {"score": 101}},
        {"signal": "BUY", "analysis": {"score": float("nan")}},
        {"signal": "BUY", "analysis": {"score": float("inf")}},
        {"signal": "UNKNOWN", "analysis": {"score": 90}},
    )
    for result in invalid_results:
        assert closed_panel_signal(result) == ("INDISPONÍVEL", "—", "#7F8B97")


def test_closed_panel_signal_does_not_round_score_up_into_a_stronger_band():
    # Fractional scores retain their actual band; display truncation must not
    # promote 69.9 to MODERADA or 79.9 to FORTE.
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": 69.9}})[1] == (
        "69% · FRACA"
    )
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": 79.9}})[1] == (
        "79% · MODERADA"
    )
