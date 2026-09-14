from decimal import Decimal
from datetime import datetime, timezone

from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage
from core.point_value_engine import PointValueRequest


def request(**overrides):
    values=dict(request_id="req-1",profile_id="profile-1",symbol="EURUSD",requested_leverage=Decimal("10"),capital_allocated=Decimal("1000"),quantity=Decimal("1"),price=Decimal("1.1"),stop_distance=Decimal("0.001"),value_per_price_unit=Decimal("100000"),maximum_loss=Decimal("200"),margin_required=Decimal("1000"),environment="DEMO"); values.update(overrides); return LeverageRequest(**values)


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


def test_leverage_can_derive_point_value_from_broker_tick_data():
    point_request = PointValueRequest(
        instrument="EURUSD", broker="ICMarkets", account_currency="USD", quote_currency="USD",
        quantity=Decimal("1"), price=Decimal("1.1"), tick_size=Decimal("0.00001"), tick_value=Decimal("1"),
        point_size=Decimal("0.0001"), as_of=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        now=datetime(2026, 9, 14, 12, 0, 1, tzinfo=timezone.utc),
    )
    result = assess_leverage(request(value_per_price_unit=None, point_value_request=point_request))
    assert result.status is LeverageStatus.ACCEPTABLE
    assert result.loss_at_stop == Decimal("100.0000")
    assert result.execution_authorized is False


def test_leverage_reassesses_when_dynamic_point_conversion_is_stale():
    point_request = PointValueRequest(
        instrument="EURGBP", broker="provider", account_currency="USD", quote_currency="GBP", quantity=Decimal("1"),
        price=Decimal("0.85"), point_size=Decimal("0.0001"), contract_size=Decimal("100000"), quote_to_account_rate=Decimal("1.25"),
        as_of=datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc), now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        conversion_max_age_seconds=Decimal("30"),
    )
    result = assess_leverage(request(symbol="EURGBP", price=Decimal("0.85"), value_per_price_unit=None, point_value_request=point_request))
    assert result.status is LeverageStatus.REASSESS
    assert "conversion_rate_is_stale" in result.reasons
