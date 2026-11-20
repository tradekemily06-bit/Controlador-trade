from streamlit_panel.presentation import closed_panel_signal


def test_closed_panel_signal_maps_buy_sell_and_wait_with_score_bands():
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": 69}}) == (
        "↑ COMPRAR", "69% · FRACA", "#46D6AD"
    )
    assert closed_panel_signal({"signal": "SELL", "analysis": {"score": 70}}) == (
        "↓ VENDER", "70% · MODERADA", "#FF667A"
    )
    assert closed_panel_signal({"signal": "WAIT", "analysis": {"score": 80}}) == (
        "AGUARDAR", "80% · FORTE", "#E8C66A"
    )


def test_closed_panel_signal_rejects_missing_or_untrusted_values():
    unavailable = ("INDISPONÍVEL", "—", "#7F8B97")
    assert closed_panel_signal(None) == unavailable
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": None}}) == unavailable
    assert closed_panel_signal({"signal": "UNKNOWN", "analysis": {"score": 90}}) == unavailable
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": True}}) == unavailable
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": 0}}) == unavailable
    assert closed_panel_signal({"signal": "BUY", "analysis": {"score": 101}}) == unavailable
