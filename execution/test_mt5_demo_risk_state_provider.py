from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from execution.mt5_demo_risk_state_provider import (
    MT5DemoRiskStateConfig,
    MT5DemoRiskStateProvider,
    MT5RiskStateProviderError,
)


NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 7
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_OUT_BY = 3

    def __init__(self, *, demo=True):
        self.demo = demo
        self.initialized = 0
        self.shutdowns = 0
        self.account = SimpleNamespace(
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if demo else 8,
            balance=1000.0,
            equity=975.0,
            profit=-25.0,
        )
        self.positions = []
        self.deals = []
        self.ticks = {}
        self.symbols = {}
        self.rates = {}

    def initialize(self):
        self.initialized += 1
        return True

    def shutdown(self):
        self.shutdowns += 1

    def account_info(self):
        return self.account

    def positions_get(self):
        return self.positions

    def history_deals_get(self, _start, _end):
        return self.deals

    def symbol_info(self, symbol):
        return self.symbols.get(symbol)

    def symbol_info_tick(self, symbol):
        return self.ticks.get(symbol)

    def copy_rates_from_pos(self, symbol, timeframe, _start_pos, _count):
        return self.rates.get((symbol, timeframe), [])


def deal(*, entry, profit, time_msc):
    return SimpleNamespace(
        entry=entry,
        profit=profit,
        swap=0.0,
        commission=0.0,
        fee=0.0,
        time_msc=time_msc,
        time=time_msc // 1000,
    )


def test_provider_reads_complete_authoritative_demo_state_and_shuts_down():
    mt5 = FakeMT5()
    mt5.positions = [
        SimpleNamespace(symbol="EURUSD", volume=0.20, type=mt5.POSITION_TYPE_BUY, price_current=1.10),
        SimpleNamespace(symbol="GBPUSD", volume=0.10, type=mt5.POSITION_TYPE_SELL, price_current=1.25),
        SimpleNamespace(symbol="EURUSD", volume=0.05, type=mt5.POSITION_TYPE_SELL, price_current=1.11),
    ]
    mt5.symbols = {
        "EURUSD": SimpleNamespace(trade_contract_size=100000.0),
        "GBPUSD": SimpleNamespace(trade_contract_size=100000.0),
    }
    mt5.deals = [
        deal(entry=mt5.DEAL_ENTRY_IN, profit=0.0, time_msc=1000),
        deal(entry=mt5.DEAL_ENTRY_OUT, profit=-10.0, time_msc=2000),
        deal(entry=mt5.DEAL_ENTRY_IN, profit=0.0, time_msc=3000),
        deal(entry=mt5.DEAL_ENTRY_OUT, profit=-5.0, time_msc=4000),
    ]
    mt5.ticks["EURUSD"] = SimpleNamespace(bid=1.10, ask=1.11)
    mt5.rates[("EURUSD", 5)] = [{"time": int(NOW.timestamp())}]

    provider = MT5DemoRiskStateProvider(
        MT5DemoRiskStateConfig(symbol="EURUSD", timeframe=5),
        mt5_module=mt5,
        now=lambda: NOW,
    )

    state = provider.current_risk_state()

    assert state.balance == 1000.0
    assert state.equity == 975.0
    assert state.realized_pnl == -15.0
    assert state.unrealized_pnl == -25.0
    assert state.trades_today == 2
    assert state.consecutive_losses == 2
    assert state.open_positions == 2
    assert state.net_position == 0.15
    assert state.exposure == pytest.approx(0.20 * 1.10 * 100000 + 0.05 * 1.11 * 100000)
    assert state.market_open is True
    assert state.last_processed_candle == NOW
    assert mt5.initialized == 1
    assert mt5.shutdowns == 1


def test_provider_without_symbol_scope_aggregates_all_positions():
    mt5 = FakeMT5()
    mt5.positions = [
        SimpleNamespace(symbol="EURUSD", volume=0.20, type=mt5.POSITION_TYPE_BUY, price_current=1.10),
        SimpleNamespace(symbol="GBPUSD", volume=0.10, type=mt5.POSITION_TYPE_SELL, price_current=1.25),
    ]
    mt5.symbols = {
        "EURUSD": SimpleNamespace(trade_contract_size=100000.0),
        "GBPUSD": SimpleNamespace(trade_contract_size=100000.0),
    }

    provider = MT5DemoRiskStateProvider(mt5_module=mt5, now=lambda: NOW)
    state = provider.current_risk_state()

    assert state.open_positions == 2
    assert state.net_position == pytest.approx(0.10)
    assert state.exposure == pytest.approx(0.20 * 1.10 * 100000 + 0.10 * 1.25 * 100000)


def test_provider_fails_closed_for_non_demo_account_and_always_shuts_down():
    mt5 = FakeMT5(demo=False)
    provider = MT5DemoRiskStateProvider(mt5_module=mt5, now=lambda: NOW)

    with pytest.raises(MT5RiskStateProviderError):
        provider.current_risk_state()

    assert mt5.shutdowns == 1


def test_provider_fails_closed_when_required_history_is_unavailable():
    mt5 = FakeMT5()
    mt5.deals = None
    provider = MT5DemoRiskStateProvider(mt5_module=mt5, now=lambda: NOW)

    with pytest.raises(MT5RiskStateProviderError):
        provider.current_risk_state()

    assert mt5.shutdowns == 1


def test_provider_keeps_optional_market_and_candle_fields_unknown_when_unsupported():
    mt5 = FakeMT5()
    provider = MT5DemoRiskStateProvider(
        MT5DemoRiskStateConfig(symbol="EURUSD", timeframe=5),
        mt5_module=mt5,
        now=lambda: NOW,
    )
    del mt5.symbol_info_tick
    del mt5.copy_rates_from_pos

    state = provider.current_risk_state()

    assert state.market_open is None
    assert state.last_processed_candle is None
