from datetime import datetime, timezone

from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_fingerprint


def make_state(**changes):
    values = {
        "balance": 1000.0,
        "equity": 995.0,
        "realized_pnl": -5.0,
        "unrealized_pnl": 0.0,
        "trades_today": 2,
        "consecutive_losses": 1,
        "open_positions": 1,
        "net_position": 1.0,
        "exposure": 100.0,
        "market_open": True,
        "last_processed_candle": datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    }
    values.update(changes)
    return OperationalState(**values)


def test_same_risk_state_has_same_fingerprint():
    assert risk_state_fingerprint(make_state()) == risk_state_fingerprint(make_state())


def test_each_risk_relevant_field_changes_identity():
    baseline = make_state()
    fields = {
        "balance": 999.0,
        "equity": 994.0,
        "realized_pnl": -6.0,
        "unrealized_pnl": 1.0,
        "trades_today": 3,
        "consecutive_losses": 2,
        "open_positions": 2,
        "net_position": 2.0,
        "exposure": 200.0,
        "market_open": False,
        "last_processed_candle": datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc),
    }
    expected = risk_state_fingerprint(baseline)
    for field, value in fields.items():
        assert risk_state_fingerprint(make_state(**{field: value})) != expected, field


def test_unknown_values_are_not_coerced_to_zero():
    unknown = make_state(balance=None, equity=None, open_positions=None, exposure=None)
    zero = make_state(balance=0.0, equity=0.0, open_positions=0, exposure=0.0)
    assert risk_state_fingerprint(unknown) != risk_state_fingerprint(zero)
