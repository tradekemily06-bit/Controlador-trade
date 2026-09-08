import math
from datetime import datetime, timezone

import pytest

from core.operational_state import (
    OperationalState,
    OperationalStateValidationError,
)
from core.risk_manager import RiskManager


def valid_state(**overrides):
    values = dict(
        balance=1000.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
        open_positions=0,
        market_open=True,
        last_processed_candle=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return OperationalState(**values)


def test_operational_state_is_immutable():
    state = valid_state()

    with pytest.raises((AttributeError, TypeError)):
        state.trades_today = 1


@pytest.mark.parametrize(
    "field",
    [
        "balance",
        "equity",
        "realized_pnl",
        "unrealized_pnl",
        "net_position",
        "exposure",
    ],
)
@pytest.mark.parametrize(
    "bad",
    [math.nan, math.inf, -math.inf, True],
)
def test_numeric_fields_reject_invalid_values(field, bad):
    with pytest.raises(OperationalStateValidationError):
        valid_state(**{field: bad})


@pytest.mark.parametrize(
    "field",
    [
        "trades_today",
        "consecutive_losses",
        "open_positions",
    ],
)
@pytest.mark.parametrize(
    "bad",
    [-1, 1.5, True],
)
def test_counters_reject_invalid_values(field, bad):
    with pytest.raises(OperationalStateValidationError):
        valid_state(**{field: bad})


def test_unknown_risk_fields_never_approve():
    state = OperationalState(realized_pnl=0.0)

    decision = RiskManager(max_operations=5).evaluate(state=state)

    assert decision.allowed is False


def test_missing_state_never_approves():
    decision = RiskManager(max_operations=5).evaluate()

    assert decision.allowed is False


def test_max_operations_blocks():
    manager = RiskManager(max_operations=5)

    decision = manager.evaluate(
        state=valid_state(trades_today=5)
    )

    assert decision.allowed is False


def test_max_consecutive_losses_blocks():
    manager = RiskManager(max_consecutive_losses=3)

    decision = manager.evaluate(
        state=valid_state(consecutive_losses=3)
    )

    assert decision.allowed is False


def test_daily_loss_limit_blocks():
    manager = RiskManager(daily_loss_limit=100)

    assert not manager.evaluate(
        state=valid_state(realized_pnl=-100)
    ).allowed

    assert manager.evaluate(
        state=valid_state(realized_pnl=-99.99)
    ).allowed


def test_valid_state_can_be_approved():
    manager = RiskManager(
        daily_loss_limit=100,
        max_operations=5,
        max_consecutive_losses=3,
    )

    decision = manager.evaluate(
        state=valid_state(
            realized_pnl=-50,
            trades_today=2,
            consecutive_losses=1,
        )
    )

    assert decision.allowed is True
