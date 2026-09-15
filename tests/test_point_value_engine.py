from datetime import datetime, timezone
from decimal import Decimal

from core.point_value_engine import PointValueRequest, PointValueSource, PointValueStatus, assess_point_value


def test_tick_value_converts_to_point_and_money_without_leverage_double_counting():
    request = PointValueRequest(
        instrument="EURUSD",
        broker="ICMarkets",
        account_currency="USD",
        quote_currency="USD",
        quantity=Decimal("1"),
        price=Decimal("1.1000"),
        tick_size=Decimal("0.00001"),
        tick_value=Decimal("1"),
        point_size=Decimal("0.00010"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.00100"))
    assert result.status is PointValueStatus.READY
    assert result.source is PointValueSource.BROKER_TICK_VALUE
    assert result.value_per_price_unit == Decimal("100000")
    assert result.value_per_point == Decimal("10.00000")
    assert result.movement_points == Decimal("10")
    assert result.movement_money == Decimal("100.00000")


def test_cross_currency_conversion_uses_current_rate_and_timestamp():
    stamp = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    request = PointValueRequest(
        instrument="EURGBP",
        broker="provider",
        account_currency="USD",
        quote_currency="GBP",
        quantity=Decimal("1"),
        price=Decimal("0.8500"),
        point_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        quote_to_account_rate=Decimal("1.2500"),
        as_of=stamp,
        now=datetime(2026, 9, 14, 12, 0, 1, tzinfo=timezone.utc),
        conversion_max_age_seconds=Decimal("5"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.0002"))
    assert result.status is PointValueStatus.READY
    assert result.value_per_point == Decimal("12.50000")
    assert result.movement_money == Decimal("25.00000")


def test_stale_conversion_requires_reassessment_instead_of_using_old_rate():
    stamp = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    request = PointValueRequest(
        instrument="EURGBP",
        broker="provider",
        account_currency="USD",
        quote_currency="GBP",
        quantity=Decimal("1"),
        price=Decimal("0.8500"),
        point_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        quote_to_account_rate=Decimal("1.2500"),
        as_of=stamp,
        now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        conversion_max_age_seconds=Decimal("30"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.0002"))
    assert result.status is PointValueStatus.REASSESS
    assert "conversion_rate_is_stale" in result.reasons
    assert result.movement_money is None


def test_same_currency_does_not_require_conversion_rate():
    request = PointValueRequest(
        instrument="XAUUSD",
        broker="provider",
        account_currency="USD",
        quote_currency="USD",
        quantity=Decimal("1"),
        price=Decimal("2500"),
        point_size=Decimal("0.1"),
        contract_size=Decimal("100"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.3"))
    assert result.status is PointValueStatus.READY
    assert result.value_per_point == Decimal("10.0")
    assert result.movement_points == Decimal("3")
    assert result.movement_money == Decimal("30.0")


def test_no_broker_value_source_is_not_guessed():
    request = PointValueRequest(
        instrument="UNKNOWN",
        broker="provider",
        account_currency="USD",
        quote_currency="USD",
        quantity=Decimal("1"),
        price=Decimal("10"),
        point_size=Decimal("0.1"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.1"))
    assert result.status is PointValueStatus.REASSESS
    assert "broker_value_source_required" in result.reasons


def test_concordant_value_sources_are_reconciled_without_artificial_preference():
    request = PointValueRequest(
        instrument="EURUSD",
        broker="provider",
        account_currency="USD",
        quote_currency="USD",
        quantity=Decimal("1"),
        price=Decimal("1.1000"),
        tick_size=Decimal("0.00001"),
        tick_value=Decimal("1"),
        point_size=Decimal("0.00010"),
        contract_size=Decimal("100000"),
        value_per_price_unit=Decimal("100000"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.00100"))
    assert result.status is PointValueStatus.READY
    assert result.value_per_price_unit == Decimal("100000")
    assert "multiple_value_sources_concordant" in result.reasons


def test_conflicting_value_sources_fail_closed_for_reassessment():
    request = PointValueRequest(
        instrument="EURUSD",
        broker="provider",
        account_currency="USD",
        quote_currency="USD",
        quantity=Decimal("1"),
        price=Decimal("1.1000"),
        tick_size=Decimal("0.00001"),
        tick_value=Decimal("1"),
        point_size=Decimal("0.00010"),
        contract_size=Decimal("90000"),
    )
    result = assess_point_value(request, movement_price_units=Decimal("0.00100"))
    assert result.status is PointValueStatus.REASSESS
    assert result.source is None
    assert "conflicting_value_sources" in result.reasons
    assert result.movement_money is None
