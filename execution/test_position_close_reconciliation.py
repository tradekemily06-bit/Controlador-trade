from types import SimpleNamespace

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5RealAdapter, ICMarketsMT5DemoConfig
from execution.ports import PositionCloseObservationStatus


class FakeMT5:
    ACCOUNT_TRADE_MODE_REAL = 2
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 2

    def __init__(self, *, positions=(), closing_deals=(), account_mode=2, opening_deals=None):
        self.positions = tuple(positions)
        self.closing_deals = tuple(closing_deals)
        self.account_mode = account_mode
        self.opening_deals = tuple(opening_deals or (
            SimpleNamespace(position_id=42, magic=2609001),
        ))
        self.shutdown_calls = 0
        self.order_send_calls = 0

    def initialize(self):
        return True

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.account_mode,
            login=123456,
            server="ICMarkets-Live",
        )

    def account_fingerprint(self):
        return ICMarketsMT5RealAdapter._account_fingerprint(self.account_info())

    def history_deals_get(self, **kwargs):
        if "ticket" in kwargs:
            return self.opening_deals
        if "position" in kwargs:
            return self.closing_deals
        return ()

    def history_orders_get(self, **kwargs):
        return ()

    def positions_get(self):
        return self.positions

    def order_send(self, payload):
        self.order_send_calls += 1
        return SimpleNamespace(retcode=0, order=999)

    def shutdown(self):
        self.shutdown_calls += 1

    def last_error(self):
        return (0, "ok")


def adapter_for(mt5):
    return ICMarketsMT5RealAdapter(
        config=ICMarketsMT5DemoConfig(magic=2609001),
        mt5_module=mt5,
    )


def test_real_close_reconciliation_reports_open_owned_position_without_sending_order():
    mt5 = FakeMT5(positions=(
        SimpleNamespace(ticket=42, magic=2609001),
    ))
    result = adapter_for(mt5).reconcile_position_close(
        "101",
        expected_account_fingerprint=mt5.account_fingerprint(),
    )
    assert result.status is PositionCloseObservationStatus.OPEN
    assert mt5.shutdown_calls == 1


def test_real_close_reconciliation_requires_closing_deal_when_position_is_absent():
    mt5 = FakeMT5(
        positions=(),
        closing_deals=(
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, magic=2609001),
        ),
    )
    result = adapter_for(mt5).reconcile_position_close(
        "101",
        expected_account_fingerprint=mt5.account_fingerprint(),
    )
    assert result.status is PositionCloseObservationStatus.CLOSED
    assert mt5.shutdown_calls == 1


def test_real_close_reconciliation_returns_unknown_without_broker_evidence():
    mt5 = FakeMT5(positions=(), closing_deals=())
    result = adapter_for(mt5).reconcile_position_close(
        "101",
        expected_account_fingerprint=mt5.account_fingerprint(),
    )
    assert result.status is PositionCloseObservationStatus.UNKNOWN
    assert mt5.shutdown_calls == 1


def test_real_close_reconciliation_rejects_unverified_account_type():
    mt5 = FakeMT5(account_mode=0)
    result = adapter_for(mt5).reconcile_position_close("101")
    assert result.status is PositionCloseObservationStatus.UNKNOWN
    assert mt5.shutdown_calls == 1


def test_real_close_reconciliation_rejects_different_account_fingerprint():
    mt5 = FakeMT5(positions=(SimpleNamespace(ticket=42, magic=2609001),))
    result = adapter_for(mt5).reconcile_position_close(
        "101",
        expected_account_fingerprint="0" * 32,
    )
    assert result.status is PositionCloseObservationStatus.UNKNOWN
    assert "não corresponde" in result.message
    assert mt5.shutdown_calls == 1


def test_real_close_refuses_account_fingerprint_mismatch_before_order_send():
    mt5 = FakeMT5(positions=(SimpleNamespace(ticket=42, magic=2609001),))
    result = adapter_for(mt5).close_position(
        "101",
        expected_account_fingerprint="0" * 32,
    )
    assert result.accepted is False
    assert "não corresponde" in result.message
    assert mt5.order_send_calls == 0
    assert mt5.shutdown_calls == 1


def test_real_close_requires_expected_account_fingerprint():
    mt5 = FakeMT5(positions=(SimpleNamespace(ticket=42, magic=2609001),))
    result = adapter_for(mt5).close_position("101")
    assert result.accepted is False
    assert "não corresponde" in result.message
    assert mt5.order_send_calls == 0
    assert mt5.shutdown_calls == 1
