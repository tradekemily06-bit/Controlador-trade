from types import SimpleNamespace

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionMode, ExecutionRequest


class AcceptedWithoutIdMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def initialize(self):
        return True

    def shutdown(self):
        pass

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, _symbol, _enabled):
        return True

    def symbol_info(self, _symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, _symbol):
        return SimpleNamespace(ask=100.0, bid=99.0)

    def order_check(self, _payload):
        return SimpleNamespace(retcode=0)

    def order_send(self, _payload):
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=None, deal=None)

    def last_error(self):
        return (0, "no error")


def test_mt5_success_without_external_id_becomes_unknown_through_gateway(tmp_path):
    adapter = ICMarketsMT5DemoAdapter(mt5_module=AcceptedWithoutIdMT5())
    ledger_path = tmp_path / "ledger.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    gateway = ExecutionGateway(
        adapter,
        KillSwitch(),
        ledger=ExecutionLedger(ledger_path),
        lifecycle=ExecutionLifecycleStore(lifecycle_path),
    )
    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id="mt5-accepted-without-id",
    )

    result = gateway.execute(request.request_id, request)

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert "UNKNOWN" in result.message
    assert ExecutionLedger(ledger_path).status(request.request_id) is ExecutionLedgerStatus.UNKNOWN
    assert ExecutionLifecycleStore(lifecycle_path).get(request.request_id).state is ExecutionLifecycleState.UNKNOWN
