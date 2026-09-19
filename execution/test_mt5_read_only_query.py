from types import SimpleNamespace

from core.p121_external_order_reconciliation import ExternalOrderStatus
from execution.mt5_read_only_query import MT5ReadOnlyOrderQuery


class FakeMT5:
    ORDER_STATE_FILLED = 2
    ORDER_STATE_PARTIAL = 3
    ORDER_STATE_CANCELED = 4
    ORDER_STATE_REJECTED = 5
    ORDER_STATE_EXPIRED = 6
    ORDER_STATE_REQUEST_CANCEL = 7

    def __init__(self, active=(), history=(), deals=(), active_none=False, history_none=False, deals_none=False):
        self.active = active
        self.history = history
        self.deals = deals
        self.active_none = active_none
        self.history_none = history_none
        self.deals_none = deals_none
        self.calls = []

    def orders_get(self, *, ticket):
        self.calls.append(("orders_get", ticket))
        return None if self.active_none else self.active

    def history_orders_get(self, *, ticket):
        self.calls.append(("history_orders_get", ticket))
        return None if self.history_none else self.history

    def history_deals_get(self, *, ticket):
        self.calls.append(("history_deals_get", ticket))
        return None if self.deals_none else self.deals


def test_active_order_is_pending_and_never_executes():
    mt5 = FakeMT5(active=(SimpleNamespace(volume_initial=1.0, volume_current=1.0, state=0),))
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.PENDING
    assert [name for name, _ in mt5.calls] == ["orders_get"]


def test_active_partial_order_stays_unknown():
    mt5 = FakeMT5(active=(SimpleNamespace(volume_initial=1.0, volume_current=0.4, state=0),))
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.UNKNOWN


def test_history_filled_is_executed():
    mt5 = FakeMT5(history=(SimpleNamespace(state=FakeMT5.ORDER_STATE_FILLED),))
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.EXECUTED


def test_history_partial_is_unknown():
    mt5 = FakeMT5(history=(SimpleNamespace(state=FakeMT5.ORDER_STATE_PARTIAL),))
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.UNKNOWN


def test_history_rejected_without_deal_is_not_executed():
    mt5 = FakeMT5(history=(SimpleNamespace(state=FakeMT5.ORDER_STATE_REJECTED),))
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.NOT_EXECUTED


def test_history_order_with_deal_is_executed():
    mt5 = FakeMT5(
        history=(SimpleNamespace(state=FakeMT5.ORDER_STATE_REJECTED),),
        deals=(SimpleNamespace(ticket=900),),
    )
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.EXECUTED


def test_empty_queries_do_not_become_not_executed():
    mt5 = FakeMT5()
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.UNKNOWN


def test_query_failure_is_unknown():
    mt5 = FakeMT5(active_none=True)
    result = MT5ReadOnlyOrderQuery(mt5).query_order("123")
    assert result.status is ExternalOrderStatus.UNKNOWN


def test_invalid_ticket_is_unknown():
    mt5 = FakeMT5()
    result = MT5ReadOnlyOrderQuery(mt5).query_order("not-a-ticket")
    assert result.status is ExternalOrderStatus.UNKNOWN
    assert mt5.calls == []


def test_request_id_is_not_assumed_to_be_mt5_request_id():
    mt5 = FakeMT5()
    result = MT5ReadOnlyOrderQuery(mt5).query_order_by_request_id("control-123")
    assert result.status is ExternalOrderStatus.UNKNOWN
    assert result.request_id == "control-123"
    assert mt5.calls == []


def test_read_only_query_has_no_send_path():
    query = MT5ReadOnlyOrderQuery(FakeMT5())
    assert not hasattr(query, "order_send")
    assert not hasattr(query, "execute")
