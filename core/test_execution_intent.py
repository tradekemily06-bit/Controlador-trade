from datetime import datetime, timezone

import pytest

from core.execution_intent import ExecutionIntent
from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_intent(**overrides):
    values = {
        "request_id": "req-001",
        "symbol": "EURUSD",
        "signal": Signal.COMPRA,
        "amount": 10.0,
        "duration_seconds": 60,
        "mode": ExecutionMode.DEMO,
        "created_at": NOW,
    }
    values.update(overrides)
    return ExecutionIntent(**values)


def test_valid_intent_is_immutable_and_explicit():
    intent = make_intent()
    assert intent.request_id == "req-001"
    assert intent.mode is ExecutionMode.DEMO
    with pytest.raises((AttributeError, TypeError)):
        intent.amount = 20.0


def test_aguardar_cannot_become_execution_intent():
    with pytest.raises(ValueError, match="AGUARDAR"):
        make_intent(signal=Signal.AGUARDAR)


def test_real_is_rejected_closed():
    with pytest.raises(ValueError, match="REAL"):
        make_intent(mode=ExecutionMode.REAL)


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", ""),
        ("symbol", ""),
        ("amount", 0),
        ("amount", float("nan")),
        ("amount", float("inf")),
        ("duration_seconds", 0),
        ("duration_seconds", True),
    ],
)
def test_invalid_values_fail_closed(field, value):
    with pytest.raises(ValueError):
        make_intent(**{field: value})


def test_created_at_must_be_datetime():
    with pytest.raises(ValueError, match="created_at"):
        make_intent(created_at="2026-01-01T00:00:00+00:00")


def test_conversion_only_builds_existing_dto_and_does_not_execute():
    intent = make_intent()
    request = intent.as_execution_request()
    assert isinstance(request, ExecutionRequest)
    assert request.symbol == "EURUSD"
    assert request.signal is Signal.COMPRA
    assert request.amount == 10.0
    assert request.duration_seconds == 60
    assert request.mode is ExecutionMode.DEMO
