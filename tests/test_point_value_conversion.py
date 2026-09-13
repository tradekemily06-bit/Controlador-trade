from decimal import Decimal

from core.point_value_conversion import ContractSpec, ConversionStatus, PointMoneyRequest, UnitKind, convert_price_movement


def test_point_conversion_to_money():
    spec = ContractSpec("demo", "EURUSD", "forex", UnitKind.POINT, Decimal("0.0001"), Decimal("10"))
    result = convert_price_movement(spec, PointMoneyRequest(Decimal("0.0003"), Decimal("2")))
    assert result.status is ConversionStatus.AVAILABLE
    assert result.units == Decimal("3")
    assert result.monetary_impact == Decimal("60")


def test_missing_value_needs_data():
    spec = ContractSpec("demo", "EURUSD", "forex", UnitKind.POINT, Decimal("0.0001"), None)
    result = convert_price_movement(spec, PointMoneyRequest(Decimal("0.0001")))
    assert result.status is ConversionStatus.NEEDS_DATA


def test_currency_conversion_requires_fx_and_applies_it():
    spec = ContractSpec("demo", "XAUUSD", "commodity", UnitKind.POINT, Decimal("0.1"), Decimal("2"), quote_currency="USD", account_currency="EUR")
    result = convert_price_movement(spec, PointMoneyRequest(Decimal("0.2"), Decimal("1"), Decimal("0.9")))
    assert result.status is ConversionStatus.AVAILABLE
    assert result.monetary_impact == Decimal("3.6")


def test_non_finite_input_is_rejected():
    spec = ContractSpec("demo", "EURUSD", "forex", UnitKind.POINT, Decimal("0.0001"), Decimal("10"))
    result = convert_price_movement(spec, PointMoneyRequest(Decimal("NaN")))
    assert result.status is ConversionStatus.INVALID
