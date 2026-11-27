from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from integration.mt5_relay_store import MT5RelayError, MT5RelayStore


def _payload(source_id: str, message_id: str, candle_at: datetime) -> dict:
    return {
        "symbol": "EURUSD",
        "timeframe": "M5",
        "account_mode": "DEMO",
        "message_id": message_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "candles": [{
            "timestamp": candle_at.isoformat(),
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 100,
        }],
    }


def test_relay_rejects_a_different_source_without_erasing_bound_source(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="account-one")
    first_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    second_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    first = _payload("account-one", str(uuid4()), first_time)
    second = _payload("account-two", str(uuid4()), second_time)
    store.ingest(first)

    with pytest.raises(MT5RelayError, match="origem vinculada"):
        store.ingest(second)

    candles = store.fetch(SimpleNamespace(symbol="EURUSD", timeframe="M5", limit=20))
    assert len(candles) == 1
    assert candles[0].timestamp == first_time

def test_replayed_old_source_message_cannot_clear_current_source_candles(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3")
    first_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    second_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    first = _payload("account-one", str(uuid4()), first_time)
    second = _payload("account-two", str(uuid4()), second_time)
    store.ingest(first)
    store.ingest(second)

    with pytest.raises(MT5RelayError, match="mensagem repetida"):
        store.ingest(first)

    candles = store.fetch(SimpleNamespace(symbol="EURUSD", timeframe="M5", limit=20))
    assert len(candles) == 1
    assert candles[0].timestamp == second_time

def test_relay_rejects_payload_source_not_matching_provisioned_source(tmp_path):
    store = MT5RelayStore(tmp_path / "relay.sqlite3", expected_source_id="account-one")
    payload = _payload("account-two", str(uuid4()), datetime.now(timezone.utc) - timedelta(minutes=5))

    with pytest.raises(MT5RelayError, match="origem provisionada"):
        store.ingest(payload)

    assert store.status()["stored_candles"] == 0
