from decimal import Decimal

from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage
from core.point_value_engine import PointValueRequest


def _point_request() -> PointValueRequest:
    return PointValueRequest(
        instrument="EURUSD",
        broker="provider",
        account_currency="USD",
        quote_currency="USD",
        quantity=Decimal("1"),
        price=Decimal("1.1000"),
        tick_size=Decimal("0.00001"),
        tick_value=Decimal("1"),
        point_size=Decimal("0.00010"),
    )


def test_leverage_requires_explicit_broker_margin_model():
    request = LeverageRequest(
        request_id="r1",
        profile_id="p1",
        symbol="EURUSD",
        requested_leverage=Decimal("10"),
        capital_allocated=Decimal("1000"),
        quantity=Decimal("1"),
        price=Decimal("1.1"),
        stop_distance=Decimal("0.001"),
        value_per_price_unit=Decimal("100000"),
        maximum_loss=Decimal("100"),
    )
    result = assess_leverage(request)
    assert result.status is LeverageStatus.REASSESS
    assert "broker_margin_model_required" in result.reasons


def test_leverage_does_not_double_count_point_value_with_leverage():
    request = LeverageRequest(
        request_id="r2",
        profile_id="provider",
        symbol="EURUSD",
        requested_leverage=Decimal("10"),
        capital_allocated=Decimal("1000"),
        quantity=Decimal("1"),
        price=Decimal("1.1"),
        stop_distance=Decimal("0.001"),
        value_per_price_unit=None,
        maximum_loss=Decimal("100"),
        point_value_request=_point_request(),
        margin_required=Decimal("100"),
    )
    result = assess_leverage(request)
    assert result.status is LeverageStatus.ACCEPTABLE
    assert result.exposure == Decimal("10000")
    assert result.loss_at_stop == Decimal("100")


def test_conflicting_explicit_and_dynamic_point_values_require_reassessment():
    request = LeverageRequest(
        request_id="r3",
        profile_id="provider",
        symbol="EURUSD",
        requested_leverage=Decimal("10"),
        capital_allocated=Decimal("1000"),
        quantity=Decimal("1"),
        price=Decimal("1.1"),
        stop_distance=Decimal("0.001"),
        value_per_price_unit=Decimal("90000"),
        maximum_loss=Decimal("100"),
        point_value_request=_point_request(),
        margin_required=Decimal("100"),
    )
    result = assess_leverage(request)
    assert result.status is LeverageStatus.REASSESS
    assert "conflicting_point_value_sources" in result.reasons
