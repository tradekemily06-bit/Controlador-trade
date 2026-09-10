from types import SimpleNamespace

from execution.mt5_demo_health import check_mt5_demo_health


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2

    def __init__(self, trade_mode=2, initialize_ok=True):
        self.trade_mode = trade_mode
        self.initialize_ok = initialize_ok
        self.calls = []

    def initialize(self):
        self.calls.append("initialize")
        return self.initialize_ok

    def account_info(self):
        self.calls.append("account_info")
        return SimpleNamespace(trade_mode=self.trade_mode) if self.initialize_ok else None

    def shutdown(self):
        self.calls.append("shutdown")

    def last_error(self):
        return (1, "fake error")


def test_health_is_read_only_and_accepts_demo():
    mt5 = FakeMT5()
    result = check_mt5_demo_health(mt5)

    assert result.available is True
    assert result.demo_account is True
    assert mt5.calls == ["initialize", "account_info", "shutdown"]


def test_health_rejects_non_demo_account():
    mt5 = FakeMT5(trade_mode=0)
    result = check_mt5_demo_health(mt5)

    assert result.available is False
    assert result.demo_account is False
    assert "DEMO" in result.message
    assert mt5.calls == ["initialize", "account_info", "shutdown"]


def test_health_never_sends_orders():
    mt5 = FakeMT5()
    result = check_mt5_demo_health(mt5)

    assert result.available is True
    assert not any("order" in str(call).lower() for call in mt5.calls)
