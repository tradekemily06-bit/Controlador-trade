"""Broker/asset-agnostic price movement to account-currency conversion.

This module deliberately refuses to invent contract specifications. A broker/symbol
must provide the actual tick/point contract and, when necessary, an FX conversion.
It is calculation support only and never grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional


class UnitKind(str, Enum):
    POINT = "point"
    PIP = "pip"
    TICK = "tick"
    PRICE_INCREMENT = "price_increment"


class ConversionStatus(str, Enum):
    AVAILABLE = "available"
    NEEDS_DATA = "needs_data"
    INVALID = "invalid"


@dataclass(frozen=True)
class ContractSpec:
    broker: str
    symbol: str
    asset_class: str
    unit_kind: UnitKind
    unit_size: Decimal
    value_per_unit: Optional[Decimal]
    contract_size: Optional[Decimal] = None
    quote_currency: Optional[str] = None
    account_currency: Optional[str] = None

@dataclass(frozen=True)
class PointMoneyRequest:
    movement: Decimal
    quantity: Decimal = Decimal("1")
    fx_to_account: Optional[Decimal] = None

@dataclass(frozen=True)
class PointMoneyResult:
    status: ConversionStatus
    broker: str
    symbol: str
    asset_class: str
    unit_kind: UnitKind
    price_movement: Decimal
    units: Optional[Decimal]
    value_per_unit_account: Optional[Decimal]
    monetary_impact: Optional[Decimal]
    missing_data: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()


def _finite_positive(value: Decimal) -> bool:
    return value.is_finite() and value > 0


def convert_price_movement(spec: ContractSpec, request: PointMoneyRequest) -> PointMoneyResult:
    """Convert a price movement into account currency using supplied contract data."""
    try:
        movement = Decimal(str(request.movement))
        quantity = Decimal(str(request.quantity))
        unit_size = Decimal(str(spec.unit_size))
        value_per_unit = None if spec.value_per_unit is None else Decimal(str(spec.value_per_unit))
    except (InvalidOperation, ValueError):
        return PointMoneyResult(ConversionStatus.INVALID, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, Decimal("0"), None, None, None, ("movement_or_contract_input",))

    if not movement.is_finite() or not quantity.is_finite() or movement < 0 or quantity <= 0 or not _finite_positive(unit_size):
        return PointMoneyResult(ConversionStatus.INVALID, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, None, None, None, ("finite_positive_contract_inputs_required",))
    if value_per_unit is None:
        return PointMoneyResult(ConversionStatus.NEEDS_DATA, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, None, None, None, ("value_per_unit",))
    if not value_per_unit.is_finite() or value_per_unit < 0:
        return PointMoneyResult(ConversionStatus.INVALID, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, None, None, None, ("value_per_unit_invalid",))

    units = movement / unit_size
    value = value_per_unit
    assumptions: list[str] = []
    if spec.account_currency and spec.quote_currency and spec.account_currency != spec.quote_currency:
        if request.fx_to_account is None:
            return PointMoneyResult(ConversionStatus.NEEDS_DATA, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, units, None, None, ("fx_to_account",))
        try:
            fx = Decimal(str(request.fx_to_account))
        except (InvalidOperation, ValueError):
            return PointMoneyResult(ConversionStatus.INVALID, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, units, None, None, ("fx_to_account_invalid",))
        if not _finite_positive(fx):
            return PointMoneyResult(ConversionStatus.INVALID, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, units, None, None, ("fx_to_account_invalid",))
        value *= fx
        assumptions.append("account_currency_conversion_supplied_by_market_data_contract")

    impact = units * quantity * value
    return PointMoneyResult(ConversionStatus.AVAILABLE, spec.broker, spec.symbol, spec.asset_class, spec.unit_kind, movement, units, value, impact, (), tuple(assumptions))
