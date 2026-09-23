from __future__ import annotations

from types import SimpleNamespace

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter
from execution.mt5_real_adapter import MT5RealAdapter, MT5RealConfig


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, trade_mode: int, server: str = "Demo-Server") -> None:
        self.trade_mode = trade_mode
        self.server = server
        self.initialize_calls = 0
        self.shutdown_calls = 0

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def account_info(self):
        return SimpleNamespace(trade_mode=self.trade_mode, server=self.server)


def test_real_and_demo_adapters_cannot_own_same_mt5_session_at_once() -> None:
    fake = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)

    market = ICMarketsMT5DemoMarketDataAdapter(mt5_module=fake)
    real = MT5RealAdapter(MT5RealConfig(expected_server="Real-Server"), mt5_module=fake)

    assert market.connect() is True
    assert real.connect() is False
    assert fake.initialize_calls == 1
    assert fake.shutdown_calls == 0

    market.disconnect()
    assert fake.shutdown_calls == 1

    # The fake terminal remains DEMO after reconnect; REAL must stay fail-closed.
    assert real.connect() is False
    assert fake.initialize_calls == 1
    real.disconnect()
    assert fake.shutdown_calls == 2


def test_real_adapter_releases_session_when_terminal_is_not_real() -> None:
    fake = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)

    real = MT5RealAdapter(MT5RealConfig(expected_server="Demo-Server"), mt5_module=fake)
    market = ICMarketsMT5DemoMarketDataAdapter(mt5_module=fake)

    assert real.is_available() is False
    assert fake.shutdown_calls == 1
    assert market.connect() is True
    market.disconnect()


def test_two_demo_adapters_share_lifecycle_without_premature_shutdown() -> None:
    fake = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)

    first = ICMarketsMT5DemoAdapter(mt5_module=fake)
    second = ICMarketsMT5DemoAdapter(mt5_module=fake)

    assert first.connect() is True
    assert second.connect() is True
    assert fake.initialize_calls == 1

    first.disconnect()
    assert fake.shutdown_calls == 0

    second.disconnect()
    assert fake.shutdown_calls == 1
