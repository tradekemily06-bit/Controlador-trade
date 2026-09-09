import math

import pytest

from core.models import Signal
from execution.p123_broker_order import (
    BrokerOrderBoundary,
    BrokerOrderResult,
    BrokerOrderSide,
)


def test_compra_maps_to_buy():
    result = BrokerOrderBoundary.from_signal(
        request_id="req-1", symbol="EURUSD", signal=Signal.COMPRA, amount=10, duration_seconds=60
    )
    assert result.side is BrokerOrderSide.BUY


def test_venda_maps_to_sell():
    result = BrokerOrderBoundary.from_signal(
        request_id="req-2", symbol="EURUSD", signal=Signal.VENDA, amount=10, duration_seconds=60
    )
    assert result.side is BrokerOrderSide.SELL


def test_aguardar_cannot_generate_order():
    with pytest.raises(ValueError):
        BrokerOrderBoundary.from_signal(
            request_id="req-3", symbol="EURUSD", signal=Signal.AGUARDAR, amount=10, duration_seconds=60
        )


@pytest.mark.parametrize("amount", [0, -1, math.inf, math.nan])
def test_invalid_amount_fails_closed(amount):
    with pytest.raises(ValueError):
        BrokerOrderBoundary.from_signal(
            request_id="req-4", symbol="EURUSD", signal=Signal.COMPRA, amount=amount, duration_seconds=60
        )


def test_invalid_duration_fails_closed():
    with pytest.raises(ValueError):
        BrokerOrderBoundary.from_signal(
            request_id="req-5", symbol="EURUSD", signal=Signal.COMPRA, amount=10, duration_seconds=0
        )


def test_result_with_external_id_is_valid():
    result = BrokerOrderBoundary.validate_result(
        BrokerOrderResult(True, "accepted", "broker-123")
    )
    assert result.external_id == "broker-123"


def test_result_without_external_id_is_preserved_for_p120_ambiguity_handling():
    result = BrokerOrderBoundary.validate_result(BrokerOrderResult(True, "accepted"))
    assert result.accepted is True
    assert result.external_id is None


def test_invalid_result_is_rejected():
    with pytest.raises(ValueError):
        BrokerOrderBoundary.validate_result(BrokerOrderResult(True, " ", None))
