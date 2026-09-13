from decimal import Decimal

from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage


def request(**overrides):
    values = dict(
        request_id="req-1", profile_id="profile-1", symbol="EURUSD",
        requested_leverage=Decimal("10"), capital_allocated=Decimal("1000"),
        quantity=Decimal("1"), price=Decimal("1.1"), stop_distance=Decimal("0.001"),
        value_per_price_unit=Decimal("100000"), maximum_loss=Decimal("200"), environment="DEMO",
    )
    values.update(overrides)
    return LeverageRequest(**values)


def test_loss_budget_can_accept_request_without_authorizing_execution():
    result = assess_leverage(request())
    assert result.status is LeverageStatus.ACCEPTABLE
    assert result.exposure == Decimal("10000")
    assert result.margin_required == Decimal("1000")
    assert result.loss_at_stop == Decimal("100")
    assert result.scoped_block is False
    assert result.execution_authorized is False


def test_loss_budget_blocks_only_this_request():
    result = assess_leverage(request(maximum_loss=Decimal("50")))
    assert result.status is LeverageStatus.BLOCKED
    assert result.scoped_block is True
    assert "loss_exceeds_request_risk_budget" in result.reasons


def test_missing_risk_input_reassesses_and_does_not_guess():
    result = assess_leverage(request(maximum_loss=None))
    assert result.status is LeverageStatus.REASSESS
    assert result.scoped_block is True
    assert "maximum_loss_or_risk_budget_required" in result.reasons


def test_real_is_not_enabled_by_leverage_assessment():
    result = assess_leverage(request(environment="REAL"))
    assert result.status is LeverageStatus.REASSESS
    assert result.execution_authorized is False
