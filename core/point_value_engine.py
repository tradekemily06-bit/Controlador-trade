"""Dynamic point/tick/pip monetary conversion for market and leverage analysis.

The engine translates instrument movement into money. It is deliberately not a
signal engine and never authorizes an operation. Broker/instrument
specification and current FX conversion are treated as data with provenance
and freshness rather than as hard-coded universal assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class PointValueStatus(str, Enum):
    READY = "READY"
    REASSESS = "REASSESS"


class PointValueSource(str, Enum):
    BROKER_TICK_VALUE = "BROKER_TICK_VALUE"
    CONTRACT_SPECIFICATION = "CONTRACT_SPECIFICATION"
    EXPLICIT_PRICE_UNIT_VALUE = "EXPLICIT_PRICE_UNIT_VALUE"


@dataclass(frozen=True)
class PointValueRequest:
    instrument: str
    broker: str
    account_currency: str
    quote_currency: str
    quantity: Decimal
    price: Decimal
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    point_size: Decimal | None = None
    contract_size: Decimal | None = None
    value_per_price_unit: Decimal | None = None
    quote_to_account_rate: Decimal | None = None
    as_of: datetime | None = None
    now: datetime | None = None
    conversion_max_age_seconds: Decimal | None = None


@dataclass(frozen=True)
class PointValueAssessment:
    instrument: str
    broker: str
    status: PointValueStatus
    source: PointValueSource | None
    account_currency: str
    quote_currency: str
    quantity: Decimal | None
    price: Decimal | None
    tick_size: Decimal | None
    point_size: Decimal | None
    value_per_price_unit: Decimal | None
    value_per_point: Decimal | None
    value_per_tick: Decimal | None
    movement_price_units: Decimal | None
    movement_points: Decimal | None
    movement_money: Decimal | None
    quote_to_account_rate: Decimal | None
    as_of: datetime | None
    reasons: tuple[str, ...]


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non_finite_numeric_input")
    return result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def assess_point_value(request: PointValueRequest, *, movement_price_units: Decimal = Decimal("0")) -> PointValueAssessment:
    """Calculate current monetary movement without creating trading authority.

    When multiple monetary-value sources are supplied, all usable sources are
    reconciled. Concordant sources may be used together; conflicting sources
    fail closed and require reassessment instead of silently preferring one.
    """
    reasons: list[str] = []
    try:
        quantity = _decimal(request.quantity)
        price = _decimal(request.price)
        movement = _decimal(movement_price_units)
        tick_size = _decimal(request.tick_size) if request.tick_size is not None else None
        tick_value = _decimal(request.tick_value) if request.tick_value is not None else None
        point_size = _decimal(request.point_size) if request.point_size is not None else None
        contract_size = _decimal(request.contract_size) if request.contract_size is not None else None
        explicit_value = _decimal(request.value_per_price_unit) if request.value_per_price_unit is not None else None
        conversion = _decimal(request.quote_to_account_rate) if request.quote_to_account_rate is not None else None
        max_age = _decimal(request.conversion_max_age_seconds) if request.conversion_max_age_seconds is not None else None
    except Exception:
        return PointValueAssessment(request.instrument, request.broker, PointValueStatus.REASSESS, None, request.account_currency, request.quote_currency, None, None, None, None, None, None, None, None, None, None, None, None, None, ("invalid_numeric_input",))

    if not request.instrument.strip() or not request.broker.strip():
        reasons.append("instrument_and_broker_required")
    if not request.account_currency.strip() or not request.quote_currency.strip():
        reasons.append("account_and_quote_currency_required")
    if quantity <= 0 or price <= 0:
        reasons.append("quantity_and_price_must_be_positive")
    if movement < 0:
        reasons.append("movement_must_be_non_negative")
    for name, value in (("tick_size", tick_size), ("tick_value", tick_value), ("point_size", point_size), ("contract_size", contract_size), ("value_per_price_unit", explicit_value), ("quote_to_account_rate", conversion), ("conversion_max_age_seconds", max_age)):
        if value is not None and value < 0:
            reasons.append(f"{name}_must_be_non_negative")
    if tick_size is not None and tick_size == 0:
        reasons.append("tick_size_must_be_positive")
    if point_size is not None and point_size == 0:
        reasons.append("point_size_must_be_positive")
    if request.as_of is not None:
        try:
            as_of = _utc(request.as_of)
            now = _utc(request.now or datetime.now(timezone.utc))
        except Exception:
            as_of = request.as_of
            reasons.append("timestamps_must_be_timezone_aware")
        else:
            if conversion is not None and request.account_currency.upper() != request.quote_currency.upper() and max_age is not None:
                age = (now - as_of).total_seconds()
                if age < 0:
                    reasons.append("conversion_timestamp_is_in_future")
                elif Decimal(str(age)) > max_age:
                    reasons.append("conversion_rate_is_stale")
    else:
        as_of = None
        if request.account_currency.upper() != request.quote_currency.upper() and conversion is not None:
            reasons.append("conversion_timestamp_required")

    if request.account_currency.upper() != request.quote_currency.upper() and conversion is None:
        reasons.append("account_currency_conversion_required")
    if request.account_currency.upper() == request.quote_currency.upper() and conversion is not None and conversion != 1:
        reasons.append("same_currency_conversion_must_be_one")

    value_candidates: list[tuple[PointValueSource, Decimal]] = []
    if tick_value is not None:
        if tick_size is None or tick_size <= 0:
            reasons.append("tick_size_required_with_tick_value")
        else:
            value_candidates.append((PointValueSource.BROKER_TICK_VALUE, tick_value / tick_size))
    if explicit_value is not None:
        value_candidates.append((PointValueSource.EXPLICIT_PRICE_UNIT_VALUE, explicit_value))
    if contract_size is not None:
        value_candidates.append((PointValueSource.CONTRACT_SPECIFICATION, contract_size))

    source: PointValueSource | None = None
    value_per_price_unit_quote: Decimal | None = None
    if not value_candidates:
        reasons.append("broker_value_source_required")
    else:
        source = value_candidates[0][0]
        value_per_price_unit_quote = value_candidates[0][1]
        if any(candidate_value != value_per_price_unit_quote for _, candidate_value in value_candidates[1:]):
            reasons.append("conflicting_value_sources")
            source = None
            value_per_price_unit_quote = None
        elif len(value_candidates) > 1:
            reasons.append("multiple_value_sources_concordant")

    if point_size is None:
        point_size = tick_size
    if point_size is None or point_size <= 0:
        reasons.append("point_size_required")

    blocking_reasons = tuple(reason for reason in reasons if reason != "multiple_value_sources_concordant")
    if blocking_reasons or value_per_price_unit_quote is None or point_size is None:
        return PointValueAssessment(request.instrument, request.broker, PointValueStatus.REASSESS, source, request.account_currency, request.quote_currency, quantity, price, tick_size, point_size, None, None, None, movement, None, None, conversion, as_of, tuple(dict.fromkeys(reasons)))

    conversion = Decimal("1") if request.account_currency.upper() == request.quote_currency.upper() else conversion
    assert conversion is not None
    value_per_price_unit = value_per_price_unit_quote * conversion
    value_per_point = value_per_price_unit * point_size
    value_per_tick = value_per_price_unit * tick_size if tick_size is not None else None
    movement_points = movement / point_size
    movement_money = movement * value_per_price_unit * quantity
    return PointValueAssessment(request.instrument, request.broker, PointValueStatus.READY, source, request.account_currency, request.quote_currency, quantity, price, tick_size, point_size, value_per_price_unit, value_per_point, value_per_tick, movement, movement_points, movement_money, conversion, as_of, tuple(dict.fromkeys(reasons)))
