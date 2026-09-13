from decimal import Decimal

from core.point_value_conversion import (
    ContractSpec, ConversionStatus, PointMoneyRequest, UnitKind, convert_price_movement,
)


def test_point_conversion_uses_tick_contract_and_quantity():
    spec = ContractSpec("broker", "EURUSD", "forex", UnitKind.POINT, Decimal("0.0001"), Decimal("10"))
    result = convert_price_movement(spec, PointMoneyRequest(Decimal("0.0003"), Decimal("2")))
    assert result.status is ConversionStatus.AVAILABLE
    assert result.units == Decimal("3")
    assert result.monetary_impact == Decimal("60")


def test_missing_contract_value_never_invents_money():
    spec = ContractSpec("broker", "BTCUSD", "crypto", UnitKind.TICK, Decimal("0.1"), None)
    result = convert_price_movement(spec, PointMoneyRequest(Decimal("0.5")))
    assert result.status is ConversionStatus.NEEDS_DATA
    assert "value_per_unit" in result.missing_data


def test_currency_conversion_is_required_when_currencies_differ():
    spec = ContractSpec("broker", "X", "other", UnitKind.PRICE_INCREMENT, Decimal("0.1"), Decimal("2"), quote_currency="USD", account_currency="BRL")
    missing = convert_price_movement(spec, PointMoneyRequest(Decimal("0.5")))
    assert missing.status is ConversionStatus.NEEDS_DATA
    converted = convert_price_movement(spec, PointMoneyRequest(Decimal("0.5"), fx_to_account=Decimal("5")))
    assert converted.monetary_impact == Decimal("50")
