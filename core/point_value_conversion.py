"""Broker/asset-agnostic price movement to account-currency conversion."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

class UnitKind(str, Enum):
    POINT="point"; PIP="pip"; TICK="tick"; PRICE_INCREMENT="price_increment"
class ConversionStatus(str, Enum):
    AVAILABLE="available"; NEEDS_DATA="needs_data"; INVALID="invalid"
@dataclass(frozen=True)
class ContractSpec:
    broker:str; symbol:str; asset_class:str; unit_kind:UnitKind; unit_size:Decimal; value_per_unit:Decimal|None; contract_size:Decimal|None=None; quote_currency:str|None=None; account_currency:str|None=None
@dataclass(frozen=True)
class PointMoneyRequest:
    movement:Decimal; quantity:Decimal=Decimal("1"); fx_to_account:Decimal|None=None
@dataclass(frozen=True)
class PointMoneyResult:
    status:ConversionStatus; broker:str; symbol:str; asset_class:str; unit_kind:UnitKind; price_movement:Decimal; units:Decimal|None; value_per_unit_account:Decimal|None; monetary_impact:Decimal|None; missing_data:tuple[str,...]=(); assumptions:tuple[str,...]=()
def convert_price_movement(spec:ContractSpec, request:PointMoneyRequest)->PointMoneyResult:
    try:
        movement=Decimal(str(request.movement)); quantity=Decimal(str(request.quantity))
    except (InvalidOperation,ValueError):
        return PointMoneyResult(ConversionStatus.INVALID,spec.broker,spec.symbol,spec.asset_class,spec.unit_kind,Decimal("0"),None,None,None,("movement_or_quantity",))
    if not movement.is_finite() or not quantity.is_finite() or movement<0 or quantity<=0 or not spec.unit_size.is_finite() or spec.unit_size<=0:
        return PointMoneyResult(ConversionStatus.INVALID,spec.broker,spec.symbol,spec.asset_class,spec.unit_kind,movement,None,None,None,("finite_positive_movement_and_quantity_required",))
    if spec.value_per_unit is None or not spec.value_per_unit.is_finite() or spec.value_per_unit<0:
        return PointMoneyResult(ConversionStatus.NEEDS_DATA,spec.broker,spec.symbol,spec.asset_class,spec.unit_kind,movement,None,None,None,("value_per_unit",))
    units=movement/spec.unit_size; value=spec.value_per_unit; assumptions=[]
    if spec.account_currency and spec.quote_currency and spec.account_currency!=spec.quote_currency:
        if request.fx_to_account is None or not request.fx_to_account.is_finite() or request.fx_to_account<=0:
            return PointMoneyResult(ConversionStatus.NEEDS_DATA,spec.broker,spec.symbol,spec.asset_class,spec.unit_kind,movement,units,None,None,("fx_to_account",))
        value*=request.fx_to_account; assumptions.append("account_currency_conversion_supplied_by_market_data_contract")
    return PointMoneyResult(ConversionStatus.AVAILABLE,spec.broker,spec.symbol,spec.asset_class,spec.unit_kind,movement,units,value,units*quantity*value,(),tuple(assumptions))
