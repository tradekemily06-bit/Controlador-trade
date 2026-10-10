from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5RealAdapter
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    ACCOUNT_TRADE_MODE_REAL = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 2
    ORDER_STATE_CANCELED = 4
    ORDER_STATE_REJECTED = 5
    ORDER_STATE_EXPIRED = 6
    POSITION_TYPE_BUY = 0

    def __init__(self, check_code=0, send_result=True):
        self.check_code = check_code
        self.send_result = send_result
        self.calls = []

    def initialize(self):
        self.calls.append("initialize")
        return True

    def shutdown(self):
        self.calls.append("shutdown")

    def account_info(self):
        self.calls.append("account_info")
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, balance=1000.0, equity=1015.0, profit=15.0)

    def history_deals_get(self, *args, **kwargs):
        self.calls.append(("history_deals_get", args, kwargs))
        if kwargs.get("ticket") == 123:
            return (SimpleNamespace(ticket=123, profit=4.0),)
        if kwargs.get("ticket") == 456:
            return ()
        return (
            SimpleNamespace(entry=self.DEAL_ENTRY_OUT, profit=8.0),
            SimpleNamespace(entry=self.DEAL_ENTRY_OUT, profit=-3.0),
            SimpleNamespace(entry=self.DEAL_ENTRY_OUT, profit=-5.0),
        )

    def history_orders_get(self, *args, **kwargs):
        self.calls.append(("history_orders_get", args, kwargs))
        if kwargs.get("ticket") == 456:
            return (SimpleNamespace(ticket=456, state=self.ORDER_STATE_CANCELED),)
        return ()

    def positions_get(self):
        self.calls.append("positions_get")
        return (SimpleNamespace(type=self.POSITION_TYPE_BUY, volume=0.10, price_current=100.0),)

    def symbol_select(self, symbol, enabled):
        self.calls.append(("symbol_select", symbol, enabled))
        return True

    def symbol_info(self, symbol):
        self.calls.append(("symbol_info", symbol))
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        self.calls.append(("symbol_info_tick", symbol))
        return SimpleNamespace(ask=100.0, bid=99.0)

    def order_check(self, payload):
        self.calls.append(("order_check", payload))
        return SimpleNamespace(retcode=self.check_code)

    def order_send(self, payload):
        self.calls.append(("order_send", payload))
        if not self.send_result:
            return None
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=123456, deal=654321)

    def last_error(self):
        return (1, "fake error")


def request(mode=ExecutionMode.DEMO, signal=Signal.COMPRA):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=signal,
        amount=0.01,
        duration_seconds=60,
        mode=mode,
        request_id="test-1",
    )


def test_demo_order_checks_before_send_and_confirms():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request())

    assert result.accepted is True
    assert result.external_id == "123456"
    names = [call if isinstance(call, str) else call[0] for call in mt5.calls]
    assert names.index("order_check") < names.index("order_send")


def test_aguardar_never_reaches_mt5():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request(signal=Signal.AGUARDAR))

    assert result.accepted is False
    assert mt5.calls == []


def test_real_mode_is_blocked_before_mt5_access():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request(mode=ExecutionMode.REAL))

    assert result.accepted is False
    assert "somente DEMO" in result.message
    assert mt5.calls == []


def test_order_check_failure_blocks_send():
    mt5 = FakeMT5(check_code=10019)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request())

    assert result.accepted is False
    assert "order_check" in result.message
    assert not any(
        isinstance(call, tuple) and call[0] == "order_send" for call in mt5.calls
    )


def test_read_operational_state_uses_mt5_observations():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    state = adapter.read_operational_state()

    assert state.balance == 1000.0
    assert state.equity == 1015.0
    assert state.realized_pnl == 0.0
    assert state.realized_loss_today == 8.0
    assert state.trades_today == 3
    assert state.consecutive_losses == 2
    assert state.open_positions == 1
    assert state.net_position == 0.10
    assert state.exposure == 10.0
    assert any(call == "history_deals_get" or (isinstance(call, tuple) and call[0] == "history_deals_get") for call in mt5.calls)
    assert "positions_get" in mt5.calls


def test_query_order_reconciles_external_deal_as_executed():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)
    observation = adapter.query_order("123")
    assert observation.status.value == "EXECUTED"


def test_query_order_reconciles_canceled_external_order_as_not_executed():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)
    observation = adapter.query_order("456")
    assert observation.status.value == "NOT_EXECUTED"


class FakeOutcomeMT5(FakeMT5):
    def __init__(self, *, open_position=False, wrong_magic=False, missing_exit=False, ambiguous_position=False):
        super().__init__()
        self.open_position = open_position
        self.wrong_magic = wrong_magic
        self.missing_exit = missing_exit
        self.ambiguous_position = ambiguous_position

    def history_deals_get(self, *args, **kwargs):
        self.calls.append(("history_deals_get", args, kwargs))
        if kwargs.get("ticket") == 123:
            return (SimpleNamespace(
                ticket=123, order=123, position_id=900, magic=0 if self.wrong_magic else 2609001,
                entry=0, profit=0.0, commission=-1.0, swap=0.0, fee=0.0,
            ),)
        if kwargs.get("position") == 900:
            opening = SimpleNamespace(
                ticket=123, order=123, position_id=900, magic=2609001, entry=0,
                profit=0.0, commission=-1.0, swap=0.0, fee=0.0,
            )
            if self.missing_exit:
                return (opening,)
            if self.ambiguous_position:
                second_entry = SimpleNamespace(
                    ticket=125, order=777, position_id=900, magic=2609001, entry=0,
                    profit=0.0, commission=-0.5, swap=0.0, fee=0.0,
                )
            else:
                second_entry = None
            closing = SimpleNamespace(
                ticket=124, order=124, position_id=900, magic=2609001, entry=self.DEAL_ENTRY_OUT,
                profit=5.0, commission=-1.5, swap=0.1, fee=0.0,
            )
            return (opening, closing) if second_entry is None else (opening, second_entry, closing)
        return ()

    def history_orders_get(self, *args, **kwargs):
        self.calls.append(("history_orders_get", args, kwargs))
        return ()

    def positions_get(self):
        self.calls.append("positions_get")
        return (SimpleNamespace(ticket=900, magic=2609001),) if self.open_position else ()


def test_query_trade_outcome_uses_closed_position_net_history():
    mt5 = FakeOutcomeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=mt5).query_trade_outcome("123")

    assert result.position_id == 900
    assert result.closed is True
    assert result.outcome == "WIN"
    assert result.financial_result == 2.6
    assert result.source == "MT5_DEMO_HISTORY"
    assert result.observed_at.tzinfo is not None


def test_query_trade_outcome_never_classifies_open_position():
    mt5 = FakeOutcomeMT5(open_position=True)
    result = ICMarketsMT5DemoAdapter(mt5_module=mt5).query_trade_outcome("123")

    assert result.outcome == "UNKNOWN"
    assert result.financial_result is None
    assert result.closed is False


def test_query_trade_outcome_rejects_unowned_or_missing_exit_history():
    unowned = ICMarketsMT5DemoAdapter(mt5_module=FakeOutcomeMT5(wrong_magic=True)).query_trade_outcome("123")
    missing_exit = ICMarketsMT5DemoAdapter(mt5_module=FakeOutcomeMT5(missing_exit=True)).query_trade_outcome("123")

    assert unowned.outcome == "UNKNOWN"
    assert unowned.financial_result is None
    assert missing_exit.outcome == "UNKNOWN"
    assert missing_exit.financial_result is None
    ambiguous = ICMarketsMT5DemoAdapter(mt5_module=FakeOutcomeMT5(ambiguous_position=True)).query_trade_outcome("123")
    assert ambiguous.outcome == "UNKNOWN"
    assert ambiguous.financial_result is None


def test_risk_day_timezone_is_explicit_and_converted_to_utc():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(
        config=__import__("execution.icmarkets_mt5_demo_adapter", fromlist=["ICMarketsMT5DemoConfig"]).ICMarketsMT5DemoConfig(
            risk_day_timezone="America/Sao_Paulo"
        ),
        mt5_module=mt5,
    )
    adapter.read_operational_state()
    history_calls = [call for call in mt5.calls if isinstance(call, tuple) and call[0] == "history_deals_get"]
    assert history_calls
    start, end = history_calls[0][1]
    assert start.tzinfo is not None and end.tzinfo is not None
    assert start.utcoffset().total_seconds() == 0
    assert end.utcoffset().total_seconds() == 0


def test_utc_timezone_does_not_depend_on_tzdata(monkeypatch):
    import execution.icmarkets_mt5_demo_adapter as adapter_module
    from zoneinfo import ZoneInfoNotFoundError
    from datetime import timezone

    def missing_timezone_database(_key):
        raise ZoneInfoNotFoundError("simulated missing tzdata")

    monkeypatch.setattr(adapter_module, "ZoneInfo", missing_timezone_database)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=FakeMT5())

    assert adapter._risk_day_zone is timezone.utc


def test_invalid_risk_day_timezone_is_rejected():
    with __import__("pytest").raises(ValueError, match="timezone IANA"):
        ICMarketsMT5DemoAdapter(config=__import__("execution.icmarkets_mt5_demo_adapter", fromlist=["ICMarketsMT5DemoConfig"]).ICMarketsMT5DemoConfig(risk_day_timezone="Not/AZone"), mt5_module=FakeMT5())


class FakeRealMT5(FakeMT5):
    def account_info(self):
        self.calls.append("account_info")
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_REAL, balance=1000.0, equity=1015.0, profit=15.0)


def test_real_adapter_accepts_only_real_account_and_real_request():
    mt5 = FakeRealMT5()
    adapter = ICMarketsMT5RealAdapter(mt5_module=mt5)
    result = adapter.execute(request(mode=ExecutionMode.REAL))
    assert result.accepted is True
    assert result.external_id == "123456"


def test_real_adapter_blocks_when_terminal_is_demo():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5RealAdapter(mt5_module=mt5)
    result = adapter.execute(request(mode=ExecutionMode.REAL))
    assert result.accepted is False
    assert "DEMO" in result.message
    assert not any(
        isinstance(call, tuple) and call[0] == "order_send" for call in mt5.calls
    )


def test_real_adapter_never_accepts_demo_request():
    mt5 = FakeRealMT5()
    adapter = ICMarketsMT5RealAdapter(mt5_module=mt5)
    result = adapter.execute(request(mode=ExecutionMode.DEMO))
    assert result.accepted is False
    assert mt5.calls == []
