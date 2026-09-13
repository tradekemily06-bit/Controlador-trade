from decimal import Decimal
from core.point_value_conversion import ContractSpec, ConversionStatus, PointMoneyRequest, UnitKind, convert_price_movement

def test_point_conversion_uses_contract_and_quantity():
    spec=ContractSpec("test","EURUSD","forex",UnitKind.POINT,Decimal("0.0001"),Decimal("10")); result=convert_price_movement(spec,PointMoneyRequest(Decimal("0.0003"),Decimal("2"))); assert result.status is ConversionStatus.AVAILABLE; assert result.units==Decimal("3"); assert result.monetary_impact==Decimal("60")
def test_missing_value_needs_data():
    spec=ContractSpec("test","EURUSD","forex",UnitKind.POINT,Decimal("0.0001"),None); assert convert_price_movement(spec,PointMoneyRequest(Decimal("0.0001"))).status is ConversionStatus.NEEDS_DATA
def test_currency_conversion_required():
    spec=ContractSpec("test","XAUUSD","commodities",UnitKind.TICK,Decimal("0.1"),Decimal("1"),quote_currency="USD",account_currency="BRL"); result=convert_price_movement(spec,PointMoneyRequest(Decimal("0.2"))); assert result.status is ConversionStatus.NEEDS_DATA
def test_currency_conversion_applied_when_supplied():
    spec=ContractSpec("test","XAUUSD","commodities",UnitKind.TICK,Decimal("0.1"),Decimal("1"),quote_currency="USD",account_currency="BRL"); result=convert_price_movement(spec,PointMoneyRequest(Decimal("0.2"),Decimal("2"),Decimal("5"))); assert result.status is ConversionStatus.AVAILABLE; assert result.monetary_impact==Decimal("20")
