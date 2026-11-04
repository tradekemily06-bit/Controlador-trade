from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(self, *, demo=True, order_ok=True, send_ok=True, external_id=True):
        self.demo = demo
        self.order_ok = order_ok
        self.send_ok = send_ok
        self.external_id = external_id
        self.shutdown_calls = 0
        self.sent = []
        self.positions = []

    def initialize(self):
        return True

    def shutdown(self):
        self.shutdown_calls += 1

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 0)

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=1.1002, bid=1.1000)

    def order_check(self, payload):
        return SimpleNamespace(retcode=0 if self.order_ok else 10030)

    def order_send(self, payload):
        self.sent.append(payload)
        if "position" in payload and self.send_ok:
            self.positions = [p for p in self.positions if int(getattr(p, "ticket", -1)) != int(payload["position"])]
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE if self.send_ok else 10006,
            order=123456 if self.external_id else None,
            deal=654321 if self.external_id else None,
        )

    def history_deals_get(self, *args, **kwargs):
        ticket = kwargs.get("ticket")
        if ticket == 123456:
            return (SimpleNamespace(ticket=654321, position_id=987654),)
        return ()

    def history_orders_get(self, *args, **kwargs):
        ticket = kwargs.get("ticket")
        if ticket == 223344:
            return (SimpleNamespace(ticket=223344, position_id=987654),)
        return ()

    def positions_get(self, symbol=None):
        if symbol is None:
            return tuple(self.positions)
        return tuple(p for p in self.positions if p.symbol == symbol)

    def last_error(self):
        return (0, "ok")


def request(signal=Signal.COMPRA, mode=ExecutionMode.DEMO, amount=0.01):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=signal,
        amount=amount,
        duration_seconds=60,
        mode=mode,
        request_id="test-1",
    )


def test_demo_buy_is_sent_after_order_check():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is True
    assert result.external_id == "123456"
    assert fake.sent[0]["type"] == fake.ORDER_TYPE_BUY
    assert fake.sent[0]["volume"] == 0.01
    assert fake.shutdown_calls == 1


def test_real_request_is_blocked_before_mt5_call():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(
        request(mode=ExecutionMode.REAL)
    )

    assert result.accepted is False
    assert fake.sent == []


def test_non_demo_account_is_blocked():
    fake = FakeMT5(demo=False)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert fake.sent == []


def test_aguardar_is_blocked():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request(Signal.AGUARDAR))

    assert result.accepted is False
    assert fake.sent == []


def test_order_check_blocks_send():
    fake = FakeMT5(order_ok=False)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert fake.sent == []


def test_volume_below_symbol_minimum_is_blocked():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request(amount=0.001))

    assert result.accepted is False
    assert fake.sent == []


def test_volume_not_aligned_to_symbol_step_is_blocked():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request(amount=0.015))

    assert result.accepted is False
    assert fake.sent == []


def test_invalid_price_is_blocked():
    fake = FakeMT5()
    fake.symbol_info_tick = lambda symbol: SimpleNamespace(ask=0.0, bid=1.1000)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert fake.sent == []


def test_missing_external_id_is_not_confirmed():
    fake = FakeMT5(external_id=False)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert result.external_id is None
    assert len(fake.sent) == 1

def test_close_position_resolves_order_ticket_to_exact_owned_position():
    fake = FakeMT5()
    fake.positions = [SimpleNamespace(ticket=987654, symbol="EURUSD", volume=0.01, type=fake.POSITION_TYPE_BUY, magic=2609001)]
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).close_position("123456")
    assert result.accepted is True
    assert fake.sent[-1]["position"] == 987654
    assert fake.sent[-1]["type"] == fake.ORDER_TYPE_SELL
    assert fake.shutdown_calls == 1

def test_close_position_falls_back_to_order_history_position_id():
    fake = FakeMT5()
    fake.positions = [SimpleNamespace(ticket=987654, symbol="EURUSD", volume=0.01, type=fake.POSITION_TYPE_SELL, magic=2609001)]
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).close_position("223344")
    assert result.accepted is True
    assert fake.sent[-1]["position"] == 987654
    assert fake.sent[-1]["type"] == fake.ORDER_TYPE_BUY

def test_close_position_blocks_when_external_identity_cannot_be_resolved():
    fake = FakeMT5()
    fake.positions = [SimpleNamespace(ticket=987654, symbol="EURUSD", volume=0.01, type=fake.POSITION_TYPE_BUY, magic=2609001)]
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).close_position("999999")
    assert result.accepted is False
    assert fake.sent == []


def test_close_position_blocks_when_position_is_not_owned_by_controlador():
    fake = FakeMT5()
    fake.positions = [SimpleNamespace(ticket=123456, symbol="EURUSD", volume=0.01, type=fake.POSITION_TYPE_BUY, magic=999)]
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).close_position("123456")
    assert result.accepted is False
    assert fake.sent == []


def test_fiscal_preview_aggregates_all_position_deals_and_never_books_results():
    from datetime import datetime, timezone

    class FiscalFakeMT5(FakeMT5):
        DEAL_ENTRY_IN = 0
        DEAL_ENTRY_OUT = 1
        DEAL_ENTRY_OUT_BY = 2
        DEAL_ENTRY_INOUT = 3

        def account_info(self):
            return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, currency="USD")

        def history_deals_get(self, *args, **kwargs):
            timestamp = int(datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp())
            all_deals = (
                SimpleNamespace(entry=0, ticket=10, position_id=7, symbol="EURUSD", volume=0.02, profit=0, commission=-0.5, swap=0, fee=0, time=timestamp-100),
                SimpleNamespace(entry=1, ticket=11, position_id=7, symbol="EURUSD", volume=0.01, profit=6, commission=-0.1, swap=-0.1, fee=-0.02, time=timestamp-10),
                SimpleNamespace(entry=1, ticket=12, position_id=7, symbol="EURUSD", volume=0.01, profit=6, commission=-0.1, swap=-0.1, fee=-0.03, time=timestamp),
            )
            if "position" in kwargs:
                return tuple(d for d in all_deals if d.position_id == kwargs["position"])
            return all_deals

    fake = FiscalFakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).read_closed_deal_candidates(30)
    assert result["count"] == 1
    candidate = result["candidates"][0]
    assert candidate["ticket"] == "12"
    assert candidate["deal_count"] == 3
    assert candidate["closing_deal_count"] == 2
    assert candidate["net_result_account_currency"] == 11.05
    assert candidate["result_scope"] == "FULL_CLOSED_POSITION"
    assert result["auto_registered"] is False
    assert "todos os negócios da posição" in result["notice"]
    assert fake.shutdown_calls == 1


def test_fiscal_preview_withholds_open_or_unbalanced_positions():
    from datetime import datetime, timezone

    class FiscalFakeMT5(FakeMT5):
        DEAL_ENTRY_IN = 0
        DEAL_ENTRY_OUT = 1
        DEAL_ENTRY_OUT_BY = 2

        def account_info(self):
            return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, currency="USD")

        def history_deals_get(self, *args, **kwargs):
            timestamp = int(datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp())
            all_deals = (
                SimpleNamespace(entry=0, ticket=10, position_id=7, symbol="EURUSD", volume=0.02, profit=0, commission=-0.5, swap=0, fee=0, time=timestamp-100),
                SimpleNamespace(entry=1, ticket=11, position_id=7, symbol="EURUSD", volume=0.01, profit=6, commission=-0.1, swap=0, fee=0, time=timestamp),
                SimpleNamespace(entry=0, ticket=20, position_id=8, symbol="EURUSD", volume=0.02, profit=0, commission=-0.5, swap=0, fee=0, time=timestamp-100),
                SimpleNamespace(entry=1, ticket=21, position_id=8, symbol="EURUSD", volume=0.01, profit=6, commission=-0.1, swap=0, fee=0, time=timestamp),
            )
            if "position" in kwargs:
                return tuple(d for d in all_deals if d.position_id == kwargs["position"])
            return all_deals

        def positions_get(self, symbol=None):
            return (SimpleNamespace(ticket=7),)

    result = ICMarketsMT5DemoAdapter(mt5_module=FiscalFakeMT5()).read_closed_deal_candidates(30)
    assert result["count"] == 0
    assert result["withheld_incomplete_positions"] == 2


def test_fiscal_preview_blocks_non_demo_and_invalid_lookback():
    fake = FakeMT5(demo=False)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=fake)
    try:
        adapter.read_closed_deal_candidates(30)
    except Exception as exc:
        assert "DEMO" in str(exc)
    else:
        raise AssertionError("non-DEMO account must be blocked")
    assert fake.shutdown_calls == 1
    try:
        adapter.read_closed_deal_candidates(0)
    except ValueError as exc:
        assert "1 e 365" in str(exc)
    else:
        raise AssertionError("invalid lookback must be rejected")


def test_fiscal_preview_fails_closed_when_history_is_unavailable():
    class MissingHistoryFake(FakeMT5):
        DEAL_ENTRY_IN = 0
        DEAL_ENTRY_OUT = 1

        def account_info(self):
            return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, currency="USD")

        def history_deals_get(self, *args, **kwargs):
            return None

        def positions_get(self, symbol=None):
            return ()

    fake = MissingHistoryFake()
    try:
        ICMarketsMT5DemoAdapter(mt5_module=fake).read_closed_deal_candidates(7)
    except Exception as exc:
        assert "histórico" in str(exc)
    else:
        raise AssertionError("missing history must be rejected")
    assert fake.shutdown_calls == 1


def test_fiscal_confirmation_rereads_complete_position_for_requested_final_ticket():
    from datetime import datetime, timezone

    class FiscalFakeMT5(FakeMT5):
        DEAL_ENTRY_IN = 0
        DEAL_ENTRY_OUT = 1
        DEAL_ENTRY_OUT_BY = 2
        DEAL_ENTRY_INOUT = 3

        def account_info(self):
            return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, currency="BRL")

        def history_deals_get(self, *args, **kwargs):
            timestamp = int(datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp())
            all_deals = (
                SimpleNamespace(entry=0, ticket=101, position_id=7, symbol="WINZ26", volume=1.0, profit=0.0, commission=-1.0, swap=0.0, fee=0.0, time=timestamp-10),
                SimpleNamespace(entry=1, ticket=111, position_id=7, symbol="WINZ26", volume=0.4, profit=50.0, commission=-0.2, swap=0.0, fee=-0.1, time=timestamp-1),
                SimpleNamespace(entry=1, ticket=112, position_id=7, symbol="WINZ26", volume=0.6, profit=70.0, commission=-0.3, swap=0.0, fee=-0.2, time=timestamp),
            )
            if "position" in kwargs:
                return tuple(d for d in all_deals if d.position_id == kwargs["position"])
            return all_deals

    fake = FiscalFakeMT5()
    candidate = ICMarketsMT5DemoAdapter(mt5_module=fake).read_closed_deal_candidate("112")
    assert candidate["ticket"] == "112"
    assert candidate["net_result_account_currency"] == 118.2
    assert candidate["account_currency"] == "BRL"
    assert candidate["result_scope"] == "FULL_CLOSED_POSITION"
    assert candidate["auto_registered"] is False
    assert fake.shutdown_calls == 1


def test_fiscal_confirmation_rejects_unknown_or_non_final_ticket():
    from datetime import datetime, timezone

    class FiscalFakeMT5(FakeMT5):
        DEAL_ENTRY_IN = 0
        DEAL_ENTRY_OUT = 1
        DEAL_ENTRY_OUT_BY = 2

        def account_info(self):
            return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, currency="BRL")

        def history_deals_get(self, *args, **kwargs):
            timestamp = int(datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp())
            all_deals = (
                SimpleNamespace(entry=0, ticket=10, position_id=7, symbol="WINZ26", volume=1.0, profit=0.0, commission=0.0, swap=0.0, fee=0.0, time=timestamp-1),
                SimpleNamespace(entry=1, ticket=11, position_id=7, symbol="WINZ26", volume=1.0, profit=10.0, commission=0.0, swap=0.0, fee=0.0, time=timestamp),
            )
            if "position" in kwargs:
                return tuple(d for d in all_deals if d.position_id == kwargs["position"])
            return all_deals

    adapter = ICMarketsMT5DemoAdapter(mt5_module=FiscalFakeMT5())
    try:
        adapter.read_closed_deal_candidate("999")
    except Exception as exc:
        assert "não encontrado" in str(exc)
    else:
        raise AssertionError("unknown ticket must not be confirmed")
    try:
        adapter.read_closed_deal_candidate("10")
    except Exception as exc:
        assert "não encontrado" in str(exc)
    else:
        raise AssertionError("opening ticket must not be confirmed")
    try:
        adapter.read_closed_deal_candidate("11x")
    except ValueError as exc:
        assert "ticket MT5 inválido" in str(exc)
    else:
        raise AssertionError("non-numeric ticket must be rejected")


def test_mt5_account_fingerprint_is_stable_and_does_not_expose_login():
    from types import SimpleNamespace

    account = SimpleNamespace(login=12345678, server="ICMarketsSC-Demo")
    fingerprint = ICMarketsMT5DemoAdapter._account_fingerprint(account)
    assert len(fingerprint) == 32
    assert fingerprint == ICMarketsMT5DemoAdapter._account_fingerprint(account)
    assert "12345678" not in fingerprint
    assert ICMarketsMT5DemoAdapter._account_fingerprint(
        SimpleNamespace(login=12345678, server="")
    ) is None
    assert ICMarketsMT5DemoAdapter._account_fingerprint(
        SimpleNamespace(login=None, server="ICMarketsSC-Demo")
    ) is None
