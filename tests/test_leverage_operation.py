from decimal import Decimal

from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage


def req(**overrides):
    values = dict(request_id="r1", profile_id="p1", symbol="EURUSD", requested_leverage=Decimal("10"), capital_allocated=Decimal("1000"), quantity=Decimal("1"), price=Decimal("1.1"), stop_distance=Decimal("0.001"), value_per_price_unit=Decimal("100"), maximum_loss=Decimal("10"), environment="DEMO")
    values.update(overrides)
    return LeverageRequest(**values)


def test_acceptable_loss_budget_is_scoped_and_never_authorizes_execution():
    result = assess_leverage(req())
    assert result.status is LeverageStatus.ACCEPTABLE
    assert result.execution_authorized is False
    assert result.scoped_block is False


def test_budget_violation_blocks_only_request():
    result = assess_leverage(req(maximum_loss=Decimal("0.01")))
    assert result.status is LeverageStatus.BLOCKED
    assert result.scoped_block is True


def test_missing_maximum_loss_requires_reassessment():
    result = assess_leverage(req(maximum_loss=None))
    assert result.status is LeverageStatus.REASSESS


def test_real_environment_never_passes_this_layer():
    result = assess_leverage(req(environment="REAL"))
    assert result.status is LeverageStatus.REASSESS
    assert result.execution_authorized is False
