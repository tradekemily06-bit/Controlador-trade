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
    DEAL_ENTRY_IN = 0
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

    def initialize(self, path=None):
        self.calls.append(("initialize", path))
        self.active_path = path
        return True

    def terminal_info(self):
        from pathlib import Path
        return SimpleNamespace(path=str(Path(self.active_path).parent) if self.active_path else "")

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
            SimpleNamespace(entry=self.DEAL_ENTRY_IN, position_id=100, profit=0.0, commission=-0.5, swap=0.0, fee=0.0, time=100),
            SimpleNamespace(entry=self.DEAL_ENTRY_OUT, position_id=100, profit=4.0, commission=-0.1, swap=0.0, fee=0.0, time=200),
            # Two partial exits from one position must count as one operation.
            SimpleNamespace(entry=self.DEAL_ENTRY_OUT, position_id=100, profit=-5.0, commission=-0.1, swap=0.0, fee=0.0, time=300),
            SimpleNamespace(entry=self.DEAL_ENTRY_IN, position_id=200, profit=0.0, commission=-0.5, swap=0.0, fee=0.0, time=400),
            SimpleNamespace(entry=self.DEAL_ENTRY_OUT, position_id=200, profit=-5.0, commission=-0.1, swap=0.0, fee=0.0, time=500),
        )

    def history_orders_get(self, *args, **kwargs):
        self.calls.append(("history_orders_get", args, kwargs))
        if kwargs.get("ticket") == 456:
            return (SimpleNamespace(ticket=456, state=self.ORDER_STATE_CANCELED),)
        return ()

    def positions_get(self):
        self.calls.append("positions_get")
        return (SimpleNamespace(type=self.POSITION_TYPE_BUY, volume=0.10, price_current=100.0, identifier=999),)

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
    assert round(state.realized_pnl, 8) == -7.3
    assert round(state.realized_loss_today, 8) == 7.3
    assert state.trades_today == 2
    assert state.consecutive_losses == 2
    assert state.open_positions == 1
    assert state.net_position == 0.10
    assert state.exposure == 10.0
    assert any(call == "history_deals_get" or (isinstance(call, tuple) and call[0] == "history_deals_get") for call in mt5.calls)
    assert "positions_get" in mt5.calls


def test_netting_reversal_keeps_trade_and_loss_streak_counts_unknown():
    class NettingReversalMT5(FakeMT5):
        DEAL_ENTRY_INOUT = 3

        def history_deals_get(self, *args, **kwargs):
            if kwargs.get("ticket") is not None:
                return ()
            return (
                SimpleNamespace(
                    entry=self.DEAL_ENTRY_IN,
                    position_id=300,
                    profit=0.0,
                    commission=-0.5,
                    swap=0.0,
                    fee=0.0,
                    time=100,
                ),
                SimpleNamespace(
                    entry=self.DEAL_ENTRY_INOUT,
                    position_id=300,
                    profit=-4.0,
                    commission=-0.1,
                    swap=0.0,
                    fee=0.0,
                    time=200,
                ),
            )

        def positions_get(self):
            return ()

    state = ICMarketsMT5DemoAdapter(
        mt5_module=NettingReversalMT5()
    ).read_operational_state()

    assert state.trades_today is None
    assert state.consecutive_losses is None


def test_missing_position_identity_keeps_risk_counters_unknown():
    class MissingPositionIdentityMT5(FakeMT5):
        def history_deals_get(self, *args, **kwargs):
            return (
                SimpleNamespace(
                    entry=self.DEAL_ENTRY_OUT,
                    profit=-10.0,
                    commission=-1.0,
                    swap=0.0,
                    fee=0.0,
                ),
            )

        def positions_get(self):
            return ()

    state = ICMarketsMT5DemoAdapter(
        mt5_module=MissingPositionIdentityMT5()
    ).read_operational_state()

    assert state.realized_pnl == -11.0
    assert state.realized_loss_today is None
    assert state.trades_today is None
    assert state.consecutive_losses is None


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


def test_closed_deal_preview_returns_complete_position_components_without_booking():
    mt5 = FakeMT5()
    mt5.account_info = lambda: SimpleNamespace(trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="USD")
    opening = SimpleNamespace(entry=mt5.DEAL_ENTRY_IN, ticket=788, position_id=456,
                              symbol="EURUSD", volume=0.1, profit=0.0,
                              commission=-1.0, swap=0.0, fee=0.0, time=1793318300)
    closing = SimpleNamespace(entry=mt5.DEAL_ENTRY_OUT, ticket=789, position_id=456,
                              symbol="EURUSD", volume=0.1, profit=10.0,
                              commission=0.0, swap=-0.5, fee=0.0, time=1793318400)

    def history_deals_get(*args, **kwargs):
        if "position" in kwargs:
            return (opening, closing)
        return (closing,)

    mt5.history_deals_get = history_deals_get
    preview = ICMarketsMT5DemoAdapter(mt5_module=mt5).read_closed_deal_candidates()
    assert preview["count"] == 1
    candidate = preview["candidates"][0]
    assert candidate["ticket"] == "789"
    assert candidate["net_result_account_currency"] == 8.5
    assert candidate["account_currency"] == "USD"
    assert candidate["result_scope"] == "FULL_CLOSED_POSITION"
    assert preview["auto_registered"] is False


def test_closed_deal_preview_excludes_missing_or_non_closing_entry_types():
    mt5 = FakeMT5()
    mt5.account_info = lambda: SimpleNamespace(
        trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="USD"
    )
    mt5.history_deals_get = lambda *args, **kwargs: (
        SimpleNamespace(entry=mt5.DEAL_ENTRY_OUT, ticket=1, profit=5.0),
        SimpleNamespace(entry=None, ticket=2, profit=100.0),
        SimpleNamespace(entry=mt5.DEAL_ENTRY_IN, ticket=3, profit=200.0),
    )

    preview = ICMarketsMT5DemoAdapter(mt5_module=mt5).read_closed_deal_candidates()

    assert preview["count"] == 0
    assert preview["candidates"] == []
    assert preview["auto_registered"] is False



def test_daily_loss_budget_sums_losing_positions_without_offsetting_winners():
    class MixedResultsMT5(FakeMT5):
        def history_deals_get(self, *args, **kwargs):
            if kwargs.get("ticket") is not None:
                return ()
            return (
                SimpleNamespace(entry=self.DEAL_ENTRY_IN, position_id=100, profit=0.0, commission=0.0, swap=0.0, fee=0.0, time=100),
                SimpleNamespace(entry=self.DEAL_ENTRY_OUT, position_id=100, profit=8.0, commission=0.0, swap=0.0, fee=0.0, time=200),
                SimpleNamespace(entry=self.DEAL_ENTRY_IN, position_id=200, profit=0.0, commission=0.0, swap=0.0, fee=0.0, time=300),
                SimpleNamespace(entry=self.DEAL_ENTRY_OUT, position_id=200, profit=-7.0, commission=0.0, swap=0.0, fee=0.0, time=400),
            )

        def positions_get(self):
            return ()

    state = ICMarketsMT5DemoAdapter(mt5_module=MixedResultsMT5()).read_operational_state()

    assert state.realized_pnl == 1.0
    assert state.realized_loss_today == 7.0

    
def test_configured_terminal_path_is_pinned_before_demo_order():
    from pathlib import Path
    from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoConfig

    terminal = str(Path("C:/Program Files/MetaTrader 5/terminal64.exe"))
    fake = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(
        ICMarketsMT5DemoConfig(terminal_path=terminal),
        mt5_module=fake,
    )

    result = adapter.execute(request())

    assert result.success is True
    assert ("initialize", terminal) in fake.calls


def test_configured_terminal_path_mismatch_blocks_demo_order():
    from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoConfig

    class WrongTerminal(FakeMT5):
        def terminal_info(self):
            return SimpleNamespace(path="C:/Other/Terminal")

    terminal = "C:/Program Files/MetaTrader 5/terminal64.exe"
    fake = WrongTerminal()
    adapter = ICMarketsMT5DemoAdapter(
        ICMarketsMT5DemoConfig(terminal_path=terminal),
        mt5_module=fake,
    )

    result = adapter.execute(request())

    assert result.success is False
    assert not any(isinstance(call, tuple) and call[0] == "order_send" for call in fake.calls)
    assert "shutdown" in fake.calls

def test_closed_deal_ticket_lookup_revalidates_final_close_and_private_account_fingerprint():
    mt5 = FakeMT5()
    mt5.account_info = lambda: SimpleNamespace(
        trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO,
        currency="BRL",
        login=12345678,
        server="ICMarketsSC-Demo",
    )
    mt5.positions_get = lambda: ()
    opening = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_IN, ticket=788, position_id=456,
        symbol="WIN$N", volume=1.0, profit=0.0,
        commission=-1.0, swap=0.0, fee=0.0, time=1793318300,
    )
    closing = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_OUT, ticket=789, position_id=456,
        symbol="WIN$N", volume=1.0, profit=10.0,
        commission=0.0, swap=-0.5, fee=-0.1, time=1793318400,
    )

    def history_deals_get(*args, **kwargs):
        if kwargs.get("position") == 456:
            return (opening, closing)
        return (closing,)

    mt5.history_deals_get = history_deals_get
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    candidate = adapter.read_closed_deal_candidate("789")

    assert candidate["ticket"] == "789"
    assert candidate["position_id"] == "456"
    assert candidate["account_currency"] == "BRL"
    assert len(candidate["account_fingerprint"]) == 32
    assert "12345678" not in repr(candidate)
    assert "ICMarketsSC-Demo" not in repr(candidate)
    assert candidate["profit"] == 10.0
    assert candidate["commission"] == -1.0
    assert candidate["swap"] == -0.5
    assert candidate["fee"] == -0.1
    assert candidate["net_result_account_currency"] == 8.4
    assert candidate["deal_count"] == 2
    assert candidate["closing_deal_count"] == 1

    for invalid_ticket in ("788", "999999"):
        try:
            adapter.read_closed_deal_candidate(invalid_ticket)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"ticket {invalid_ticket} should not identify the final closing deal")

def test_closed_deal_preview_aggregates_multiple_partial_closes_for_one_position():
    mt5 = FakeMT5()
    mt5.account_info = lambda: SimpleNamespace(
        trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="BRL",
        login=12345678, server="ICMarketsSC-Demo",
    )
    mt5.positions_get = lambda: ()
    opening = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_IN, ticket=10, position_id=900,
        symbol="WIN$", volume=1.0, profit=0.0,
        commission=-0.4, swap=0.0, fee=0.0, time=1793318300,
    )
    partial_one = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_OUT, ticket=11, position_id=900,
        symbol="WIN$", volume=0.4, profit=8.0,
        commission=-0.2, swap=0.0, fee=-0.1, time=1793318350,
    )
    partial_two = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_OUT, ticket=12, position_id=900,
        symbol="WIN$", volume=0.6, profit=-2.0,
        commission=-0.3, swap=-0.1, fee=-0.2, time=1793318400,
    )

    def history_deals_get(*args, **kwargs):
        if kwargs.get("position") == 900:
            return (opening, partial_one, partial_two)
        return (partial_one, partial_two)

    mt5.history_deals_get = history_deals_get
    preview = ICMarketsMT5DemoAdapter(mt5_module=mt5).read_closed_deal_candidates()
    assert preview["count"] == 1
    candidate = preview["candidates"][0]
    assert candidate["ticket"] == "12"
    assert candidate["volume"] == 1.0
    assert candidate["profit"] == 6.0
    assert candidate["commission"] == -0.9
    assert candidate["swap"] == -0.1
    assert candidate["fee"] == -0.3
    assert candidate["net_result_account_currency"] == 4.7
    assert candidate["deal_count"] == 3
    assert candidate["closing_deal_count"] == 2


def test_closed_deal_preview_withholds_position_when_opened_and_closed_volume_do_not_match():
    mt5 = FakeMT5()
    mt5.account_info = lambda: SimpleNamespace(
        trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="BRL"
    )
    mt5.positions_get = lambda: ()
    opening = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_IN, ticket=20, position_id=901,
        symbol="WIN$", volume=1.0, profit=0.0,
        commission=0.0, swap=0.0, fee=0.0, time=1793318300,
    )
    closing = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_OUT, ticket=21, position_id=901,
        symbol="WIN$", volume=0.7, profit=5.0,
        commission=0.0, swap=0.0, fee=0.0, time=1793318400,
    )

    def history_deals_get(*args, **kwargs):
        if kwargs.get("position") == 901:
            return (opening, closing)
        return (closing,)

    mt5.history_deals_get = history_deals_get
    preview = ICMarketsMT5DemoAdapter(mt5_module=mt5).read_closed_deal_candidates()
    assert preview["count"] == 0
    assert preview["candidates"] == []
    assert preview["withheld_incomplete_positions"] == 1


def test_closed_deal_preview_withholds_position_still_reported_open_by_mt5():
    mt5 = FakeMT5()
    mt5.account_info = lambda: SimpleNamespace(
        trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="BRL"
    )
    mt5.positions_get = lambda: (
        SimpleNamespace(identifier=902, ticket=777),
    )
    opening = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_IN, ticket=30, position_id=902,
        symbol="WIN$", volume=1.0, profit=0.0,
        commission=0.0, swap=0.0, fee=0.0, time=1793318300,
    )
    closing = SimpleNamespace(
        entry=mt5.DEAL_ENTRY_OUT, ticket=31, position_id=902,
        symbol="WIN$", volume=1.0, profit=5.0,
        commission=0.0, swap=0.0, fee=0.0, time=1793318400,
    )

    def history_deals_get(*args, **kwargs):
        if kwargs.get("position") == 902:
            return (opening, closing)
        return (closing,)

    mt5.history_deals_get = history_deals_get
    preview = ICMarketsMT5DemoAdapter(mt5_module=mt5).read_closed_deal_candidates()
    assert preview["count"] == 0
    assert preview["candidates"] == []
    assert preview["withheld_incomplete_positions"] == 1

def test_closed_deal_preview_withholds_malformed_ticket_and_timestamp_metadata():
    def run_case(closing_overrides):
        mt5 = FakeMT5()
        mt5.account_info = lambda: SimpleNamespace(
            trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="BRL"
        )
        mt5.positions_get = lambda: ()
        opening = SimpleNamespace(
            entry=mt5.DEAL_ENTRY_IN, ticket=40, position_id=903,
            symbol="WIN$", volume=1.0, profit=0.0,
            commission=0.0, swap=0.0, fee=0.0, time=1793318300,
        )
        closing_values = {
            "entry": mt5.DEAL_ENTRY_OUT, "ticket": 41, "position_id": 903,
            "symbol": "WIN$", "volume": 1.0, "profit": 5.0,
            "commission": 0.0, "swap": 0.0, "fee": 0.0,
            "time": 1793318400, "time_msc": 1793318400000,
        }
        closing_values.update(closing_overrides)
        closing = SimpleNamespace(**closing_values)

        def history_deals_get(*args, **kwargs):
            if kwargs.get("position") == 903:
                return (opening, closing)
            return (closing,)

        mt5.history_deals_get = history_deals_get
        return ICMarketsMT5DemoAdapter(mt5_module=mt5).read_closed_deal_candidates()

    for malformed in (
        {"ticket": None},
        {"time_msc": "not-a-number"},
        {"time": 10**30},
    ):
        preview = run_case(malformed)
        assert preview["count"] == 0
        assert preview["candidates"] == []
        assert preview["withheld_incomplete_positions"] == 1

def test_mt5_account_fingerprint_requires_complete_positive_numeric_identity():
    fingerprint = ICMarketsMT5DemoAdapter._account_fingerprint
    valid = SimpleNamespace(login=12345678, server=" ICMarketsSC-Demo ")
    equivalent = SimpleNamespace(login="12345678", server="icmarketssc-demo")
    assert fingerprint(valid) is not None
    assert len(fingerprint(valid)) == 32
    assert fingerprint(valid) == fingerprint(equivalent)

    invalid_accounts = (
        SimpleNamespace(login=None, server="ICMarketsSC-Demo"),
        SimpleNamespace(login=0, server="ICMarketsSC-Demo"),
        SimpleNamespace(login=-1, server="ICMarketsSC-Demo"),
        SimpleNamespace(login="not-a-login", server="ICMarketsSC-Demo"),
        SimpleNamespace(login="１２３４", server="ICMarketsSC-Demo"),
        SimpleNamespace(login=12345678, server=""),
        SimpleNamespace(login=12345678, server="S" * 256),
    )
    for account in invalid_accounts:
        assert fingerprint(account) is None


def test_mt5_account_fingerprint_separates_login_and_server_pairs():
    fingerprint = ICMarketsMT5DemoAdapter._account_fingerprint
    first = fingerprint(SimpleNamespace(login=12345678, server="ICMarketsSC-Demo"))
    other_login = fingerprint(SimpleNamespace(login=87654321, server="ICMarketsSC-Demo"))
    other_server = fingerprint(SimpleNamespace(login=12345678, server="ICMarketsSC-Live"))
    assert first != other_login
    assert first != other_server
    assert other_login != other_server
