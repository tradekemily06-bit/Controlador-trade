from decimal import Decimal
from datetime import datetime, timezone

from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage
from core.point_value_engine import PointValueRequest


def test_conflicting_explicit_and_point_value_sources_reassess():
    point_request = PointValueRequest(
        instrument="EURUSD", broker="ICMarkets", account_currency="USD", quote_currency="USD",
        quantity=Decimal("1"), price=Decimal("1.1"), tick_size=Decimal("0.00001"), tick_value=Decimal("1"),
        point_size=Decimal("0.0001"), as_of=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        now=datetime(2026, 9, 14, 12, 0, 1, tzinfo=timezone.utc),
    )
    request = LeverageRequest(
        request_id="req-conflict", profile_id="profile-1", symbol="EURUSD",
        requested_leverage=Decimal("10"), capital_allocated=Decimal("1000"), quantity=Decimal("1"),
        price=Decimal("1.1"), stop_distance=Decimal("0.001"), value_per_price_unit=Decimal("90000"),
        maximum_loss=Decimal("200"), margin_required=Decimal("1000"), point_value_request=point_request,
    )
    result = assess_leverage(request)
    assert result.status is LeverageStatus.REASSESS
    assert "conflicting_point_value_sources" in result.reasons
    assert result.execution_authorized is False
