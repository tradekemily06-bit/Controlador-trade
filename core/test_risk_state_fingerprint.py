from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_identity


def _state(**overrides) -> OperationalState:
    values = {
        "balance": 1000.0,
        "equity": 995.0,
        "realized_pnl": -5.0,
        "unrealized_pnl": 2.0,
        "trades_today": 3,
        "consecutive_losses": 1,
        "open_positions": 1,
        "net_position": 0.1,
        "exposure": 100.0,
        "market_open": True,
        "last_processed_candle": datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return OperationalState(**values)


def test_risk_state_identity_is_deterministic() -> None:
    assert risk_state_identity(_state()) == risk_state_identity(_state())


def test_equivalent_instants_with_different_offsets_have_same_identity() -> None:
    utc = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)
    offset = timezone(timedelta(hours=-3))
    equivalent = utc.astimezone(offset)
    assert risk_state_identity(_state(last_processed_candle=utc)) == risk_state_identity(
        _state(last_processed_candle=equivalent)
    )


@pytest.mark.parametrize(
    "field",
    (
        "balance",
        "equity",
        "realized_pnl",
        "unrealized_pnl",
        "trades_today",
        "consecutive_losses",
        "open_positions",
        "net_position",
        "exposure",
        "market_open",
        "last_processed_candle",
    ),
)
def test_every_risk_relevant_field_changes_identity(field: str) -> None:
    baseline = _state()
    changed = {
        "balance": 1001.0,
        "equity": 996.0,
        "realized_pnl": -4.0,
        "unrealized_pnl": 3.0,
        "trades_today": 4,
        "consecutive_losses": 2,
        "open_positions": 2,
        "net_position": 0.2,
        "exposure": 101.0,
        "market_open": False,
        "last_processed_candle": datetime(2026, 9, 15, 20, 5, tzinfo=timezone.utc),
    }
    assert risk_state_identity(baseline) != risk_state_identity(_state(**{field: changed[field]}))


def test_unknown_values_are_part_of_identity_not_zero_defaults() -> None:
    complete = _state()
    unknown = _state(balance=None, equity=None, exposure=None)
    assert risk_state_identity(complete) != risk_state_identity(unknown)


def test_naive_candle_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        risk_state_identity(_state(last_processed_candle=datetime(2026, 9, 15, 20, 0)))
