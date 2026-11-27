from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid

import pytest

from data.feed import MarketDataRequest
from integration.mt5_relay_store import MT5RelayError, MT5RelayStore


def _payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "source_id": "local-demo",
        "message_id": str(uuid.uuid4()),
        "sent_at": now.isoformat(),
        "account_mode": "DEMO",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "candles": [
            {
                "timestamp": (now - timedelta(minutes=10)).isoformat(),
                "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 100
            },
            {
                "timestamp": (now - timedelta(minutes=5)).isoformat(),
                "open": 1.15, "high": 1.25, "low": 1.1, "close": 1.2, "volume": 120
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_relay_ingests_validated_demo_candles_and_serves_provider_contract(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="local-demo")
    result = store.ingest(_payload())

    candles = store.fetch(MarketDataRequest("EURUSD", "M5", 10))
    assert result["accepted"] == 2
    assert len(candles) == 2
    assert candles[-1].close == 1.2
    assert store.get_account_mode() == "DEMO"
    assert store.status()["connected"] is True


@pytest.mark.parametrize("overrides", [
    {"account_mode": "REAL"},
    {"sent_at": "2000-01-01T00:00:00+00:00"},
    {"symbol": "../EURUSD"},
    {"timeframe": "MN1"},
    {"candles": []},
])
def test_relay_rejects_unsafe_or_invalid_payloads(tmp_path, overrides):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="local-demo")
    with pytest.raises(MT5RelayError):
        store.ingest(_payload(**overrides))


def test_relay_rejects_replayed_message_id(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="local-demo")
    payload = _payload()
    store.ingest(payload)
    with pytest.raises(MT5RelayError, match="repetida"):
        store.ingest(payload)


def test_relay_fails_closed_when_heartbeat_is_stale(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="local-demo")
    store.ingest(_payload())
    with store._connect() as db:
        db.execute(
            "UPDATE mt5_relay_state SET last_seen=? WHERE singleton=1",
            ((datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),),
        )
    with pytest.raises(MT5RelayError, match="heartbeat"):
        store.get_account_mode()



def test_relay_allows_identical_overlapping_candles_without_rewriting(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="local-demo")
    payload = _payload()
    store.ingest(payload)

    overlapping = _payload(
        message_id=str(uuid.uuid4()),
        candles=[payload["candles"][0]],
    )
    result = store.ingest(overlapping)

    candles = store.fetch(MarketDataRequest("EURUSD", "M5", 10))
    assert result["accepted"] == 1
    assert len(candles) == 2
    assert candles[0].close == 1.15


def test_relay_rejects_rewriting_an_existing_candle_and_rolls_back_batch(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="local-demo")
    original = _payload()
    store.ingest(original)
    original_candles = store.fetch(MarketDataRequest("EURUSD", "M5", 10))

    changed = _payload(
        message_id=str(uuid.uuid4()),
        candles=[
            {
                **original["candles"][0],
                "close": 1.18,
                "high": 1.21,
            },
            {
                "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
                "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 80,
            },
        ],
    )
    with pytest.raises(MT5RelayError, match="histórico imutável"):
        store.ingest(changed)

    after = store.fetch(MarketDataRequest("EURUSD", "M5", 10))
    assert after == original_candles
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM mt5_relay_messages").fetchone()[0] == 1
