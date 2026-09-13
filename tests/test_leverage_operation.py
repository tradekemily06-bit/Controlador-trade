from decimal import Decimal
from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage

def request(**overrides):
    values=dict(request_id="req-1",profile_id="profile-1",symbol="EURUSD",requested_leverage=Decimal("10"),capital_allocated=Decimal("1000"),quantity=Decimal("1"),price=Decimal("1.1"),stop_distance=Decimal("0.001"),value_per_price_unit=Decimal("100000"),maximum_loss=Decimal("200"),environment="DEMO"); values.update(overrides); return LeverageRequest(**values)
def test_loss_budget_accepts_without_authorizing():
    result=assess_leverage(request()); assert result.status is LeverageStatus.ACCEPTABLE; assert result.exposure==Decimal("10000"); assert result.margin_required==Decimal("1000"); assert result.loss_at_stop==Decimal("100"); assert result.execution_authorized is False
def test_loss_budget_blocks_request():
    result=assess_leverage(request(maximum_loss=Decimal("50"))); assert result.status is LeverageStatus.BLOCKED; assert result.scoped_block is True
def test_missing_input_reassesses():
    result=assess_leverage(request(maximum_loss=None)); assert result.status is LeverageStatus.REASSESS; assert result.scoped_block is True
def test_real_not_enabled():
    result=assess_leverage(request(environment="REAL")); assert result.status is LeverageStatus.REASSESS; assert result.execution_authorized is False
def test_nonfinite_risk_input_reassesses():
    result=assess_leverage(request(maximum_loss=Decimal("NaN"))); assert result.status is LeverageStatus.REASSESS; assert "invalid_risk_numeric_input" in result.reasons
