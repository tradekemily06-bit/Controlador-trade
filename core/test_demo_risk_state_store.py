from datetime import datetime, timezone
import json

import pytest

from core.demo_risk_state_store import DemoRiskStateStore, DemoRiskStateUnavailable
from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_fingerprint


def state(**overrides):
    values = {
        "balance": 1000.0,
        "equity": 1000.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "trades_today": 2,
        "consecutive_losses": 0,
        "open_positions": 0,
        "net_position": 0.0,
        "exposure": 0.0,
        "market_open": True,
        "last_processed_candle": datetime(2026, 9, 15, 19, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return OperationalState(**values)


def test_replace_and_current_round_trip(tmp_path):
    store = DemoRiskStateStore(tmp_path / "demo-risk.json")
    expected = state()

    fingerprint = store.replace(expected, source="demo-account-adapter")

    assert fingerprint == risk_state_fingerprint(expected)
    assert store.current() == expected
    assert store.fingerprint() == fingerprint
    assert store.status()["available"] is True
    assert store.status()["source"] == "demo-account-adapter"


def test_missing_state_fails_closed(tmp_path):
    store = DemoRiskStateStore(tmp_path / "demo-risk.json")

    with pytest.raises(DemoRiskStateUnavailable):
        store.current()
    with pytest.raises(DemoRiskStateUnavailable):
        store.fingerprint()
    assert store.status()["available"] is False


def test_untrusted_source_cannot_publish(tmp_path):
    store = DemoRiskStateStore(tmp_path / "demo-risk.json")

    with pytest.raises(PermissionError):
        store.replace(state(), source="browser")


def test_missing_required_risk_fields_cannot_publish(tmp_path):
    store = DemoRiskStateStore(tmp_path / "demo-risk.json")

    with pytest.raises(DemoRiskStateUnavailable):
        store.replace(OperationalState(), source="demo-account-adapter")


def test_tampered_fingerprint_fails_closed(tmp_path):
    path = tmp_path / "demo-risk.json"
    store = DemoRiskStateStore(path)
    store.replace(state(), source="demo-account-adapter")

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state"]["trades_today"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DemoRiskStateUnavailable):
        store.fingerprint()


def test_unsupported_version_fails_closed(tmp_path):
    path = tmp_path / "demo-risk.json"
    store = DemoRiskStateStore(path)
    store.replace(state(), source="demo-account-adapter")

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DemoRiskStateUnavailable):
        store.current()
