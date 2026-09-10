from execution.icmarkets_ctrader_demo_boundary import (
    ICMarketsCTraderDemoBoundary,
    ICMarketsDemoConfig,
    ICMarketsDemoStatus,
)
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


def request(mode=ExecutionMode.DEMO):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=50,
        duration_seconds=60,
        mode=mode,
        request_id="req-icm-demo-1",
    )


def test_without_config_is_not_configured():
    boundary = ICMarketsCTraderDemoBoundary()
    assert boundary.status is ICMarketsDemoStatus.NOT_CONFIGURED
    assert boundary.is_available() is False


def test_configured_demo_waits_for_api_approval():
    boundary = ICMarketsCTraderDemoBoundary(ICMarketsDemoConfig(account_id=10111995))
    assert boundary.status is ICMarketsDemoStatus.API_PENDING_APPROVAL
    assert boundary.is_available() is False


def test_pending_boundary_never_sends_order():
    boundary = ICMarketsCTraderDemoBoundary(ICMarketsDemoConfig(account_id=10111995))
    result = boundary.execute(request())
    assert result.accepted is False
    assert "nenhuma ordem foi enviada" in result.message


def test_real_mode_is_rejected_before_connection():
    boundary = ICMarketsCTraderDemoBoundary(ICMarketsDemoConfig(account_id=10111995))
    result = boundary.execute(request(ExecutionMode.REAL))
    assert result.accepted is False
    assert "somente DEMO" in result.message
