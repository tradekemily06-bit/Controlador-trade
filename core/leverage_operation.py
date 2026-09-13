"""Operation-scoped leverage assessment; calculation only, never authorization."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

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
    if not result.is_finite(): raise ValueError("non_finite_numeric_input")
    return result

def assess_leverage(request: LeverageRequest) -> LeverageAssessment:
    reasons: list[str] = []
    try:
        leverage, capital, quantity, price = map(_decimal, (request.requested_leverage, request.capital_allocated, request.quantity, request.price))
    except Exception:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.BLOCKED, None, None, None, None, ("invalid_numeric_input",), True)
    if leverage <= 0: reasons.append("leverage_must_be_positive")
    if capital <= 0 or quantity <= 0 or price <= 0: reasons.append("capital_quantity_and_price_must_be_positive")
    if request.environment.upper() == "REAL": reasons.append("real_environment_requires_final_real_release_gate")
    if request.stop_distance is None: reasons.append("stop_distance_required_for_loss_assessment")
    if request.value_per_price_unit is None: reasons.append("value_per_price_unit_required_for_loss_assessment")
    if request.maximum_loss is None: reasons.append("maximum_loss_or_risk_budget_required")
    if reasons:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, tuple(reasons), True)
    try:
        stop_distance, value_per_unit, maximum_loss = map(_decimal, (request.stop_distance, request.value_per_price_unit, request.maximum_loss))
    except Exception:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("invalid_risk_numeric_input",), True)
    if stop_distance < 0 or value_per_unit < 0 or maximum_loss < 0:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.REASSESS, None, None, None, None, ("risk_inputs_must_be_non_negative",), True)
    exposure = capital * leverage
    margin = capital
    loss = stop_distance * value_per_unit * quantity
    loss_ratio = loss / capital
    if loss > maximum_loss:
        return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.BLOCKED, exposure, margin, loss, loss_ratio, ("loss_exceeds_request_risk_budget",), True)
    return LeverageAssessment(request.request_id, request.profile_id, LeverageStatus.ACCEPTABLE, exposure, margin, loss, loss_ratio, (), False)
