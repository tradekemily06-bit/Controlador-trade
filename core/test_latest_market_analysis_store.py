from __future__ import annotations

import pytest

from core.latest_market_analysis_store import LatestMarketAnalysisStore


def test_latest_market_analysis_survives_store_recreation(tmp_path):
    database = tmp_path / "runtime" / "latest.sqlite3"
    first = LatestMarketAnalysisStore(database)
    snapshot = {
        "signal": "BUY",
        "analysis": {"symbol": "EURUSD", "timeframe": "5m", "score": 82},
        "execution_allowed": False,
    }

    first.save("eurusd", "5M", snapshot)
    restored = LatestMarketAnalysisStore(database)

    assert restored.latest("EURUSD", "5m") == snapshot
    assert restored.latest() == snapshot
    record = restored.latest_record("EURUSD", "5m")
    assert record is not None
    assert record["analysis"] == snapshot
    assert record["updated_at"].endswith("+00:00")


def test_latest_market_analysis_keeps_symbols_and_timeframes_isolated(tmp_path):
    store = LatestMarketAnalysisStore(tmp_path / "latest.sqlite3")
    eurusd = {"signal": "BUY", "analysis": {"score": 81}}
    btcusd = {"signal": "WAIT", "analysis": {"score": 64}}

    store.save("EURUSD", "5m", eurusd)
    store.save("BTCUSD", "1h", btcusd)

    assert store.latest("EURUSD", "5m") == eurusd
    assert store.latest("BTCUSD", "1h") == btcusd
    assert store.latest("EURUSD", "1h") is None
    assert store.latest() == btcusd


def test_latest_market_analysis_rejects_partial_key_and_non_finite_payload(tmp_path):
    store = LatestMarketAnalysisStore(tmp_path / "latest.sqlite3")

    with pytest.raises(ValueError):
        store.latest("EURUSD", None)
    with pytest.raises(ValueError):
        store.save("EURUSD", "5m", {"score": float("nan")})
