

def test_analyze_uses_core_engine():
    status, data = call_app(
        "/api/analyze",
        "POST",
        {"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"},
    )
    assert status.startswith("200")
    # Legacy score-only input is no longer actionable without senior context.
    assert data["signal"] == "AGUARDAR"
    assert data["score"] == 85
    assert data["execution_allowed"] is False


def test_unconfirmed_signal_stays_wait():
    status, data = call_app("/api/analyze", "POST", {"score": 95, "confirmed": False})
    assert status.startswith("200")
    assert data["signal"] == "AGUARDAR"
