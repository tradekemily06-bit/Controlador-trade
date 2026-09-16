"""Operation-scoped leverage assessment; calculation only, never authorization."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .point_value_engine import PointValueRequest, PointValueStatus, assess_point_value


class LeverageStatus(str, Enum):
    ACCEPTABLE = "acceptable"
    REASSESS = "reassess"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class LeverageRequest:
    request_id: str
    profile_id: str
    symbol: str
    requested_leverage: Decimal
    capital_allocated: Decimal
    quantity: Decimal
    price: Decimal
    stop_distance: Decimal | None
    value_per_price_unit: Decimal | None
    maximum_loss: Decimal | None
    environment: str = "DEMO"
    point_value_request: PointValueRequest | None = None
    margin_required: Decimal | None = None


@dataclass(frozen=True)
class LeverageAssessment:
    request_id: str
    profile_id: str
    status: LeverageStatus
    exposure: Decimal | None
    margin_required: Decimal | None
    loss_at_stop: Decimal | None
    loss_ratio: Decimal | None
    reasons: tuple[str, ...]
    scoped_block: bool
    execution_authorized: bool = False


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non_finite_numeric_input")
    return result


def assess_leverage(request: LeverageRequest) -> LeverageAssessment:
    reasons: list[str] = []
    try:
        leverage, capital, quantity, price = map(_decimal, (request.requested_leverage, request.capital_allocated, request.quantity, request.price))
    except Exception:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.BLOCKED, None, None, None, None, ("invalid_numeric_input",), True)
    if leverage <= 0:
        reasons.append("leverage_must_be_positive")
    if capital <= 0 or quantity <= 0 or price <= 0:
        reasons.append("capital_quantity_and_price_must_be_positive")
    if request.environment.upper() == "REAL":
        reasons.append("real_environment_requires_final_real_release_gate")
    if request.stop_distance is None:
        reasons.append("stop_distance_required_for_loss_assessment")
    if request.value_per_price_unit is None and request.point_value_request is None:
        reasons.append("point_value_source_required_for_loss_assessment")
    if request.maximum_loss is None:
        reasons.append("maximum_loss_or_risk_budget_required")
    if request.margin_required is None:
        reasons.append("broker_margin_model_required")
    if reasons:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, tuple(reasons), True)
    try:
        stop_distance = _decimal(request.stop_distance)
        maximum_loss = _decimal(request.maximum_loss)
        explicit_value = _decimal(request.value_per_price_unit) if request.value_per_price_unit is not None else None
        margin = _decimal(request.margin_required)
    except Exception:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("invalid_risk_numeric_input",), True)
    if stop_distance < 0 or maximum_loss < 0 or (explicit_value is not None and explicit_value < 0) or margin < 0:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("risk_inputs_must_be_non_negative",), True)

    value_per_unit = explicit_value
    if request.point_value_request is not None:
        point_request = request.point_value_request
        if point_request.instrument.strip().upper() != request.symbol.strip().upper():
            return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("point_value_instrument_mismatch",), True)
        if _decimal(point_request.quantity) != quantity or _decimal(point_request.price) != price:
            return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("point_value_quantity_or_price_mismatch",), True)
        point_result = assess_point_value(point_request, movement_price_units=stop_distance)
        if point_result.status is not PointValueStatus.READY or point_result.value_per_price_unit is None:
            return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, point_result.reasons, True)
        derived_value = point_result.value_per_price_unit
        if value_per_unit is not None and derived_value != value_per_unit:
            return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("conflicting_point_value_sources",), True)
        value_per_unit = derived_value

    assert value_per_unit is not None
    exposure = capital * leverage
    loss = stop_distance * value_per_unit * quantity
    loss_ratio = loss / capital
    if loss > maximum_loss:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.BLOCKED, exposure, margin, loss, loss_ratio, ("loss_exceeds_request_risk_budget",), True)
    return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.ACCEPTABLE, exposure, margin, loss, loss_ratio, (), False)
