from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.operational_state import OperationalState
from execution.mt5_demo_risk_state_provider import (
    MT5DemoRiskStateConfig,
    MT5DemoRiskStateProvider,
    MT5RiskStateProviderError,
)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_OUT_BY = 3
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(self, *, demo=True, positions=None, deals=None, rates=None):
        self.demo = demo
        self.positions = list(positions or [])
        self.deals = list(deals or [])
        self.rates = rates if rates is not None else [SimpleNamespace(time=1778889600)]
        self.initialized = 0
        self.shutdowns = 0

    def initialize(self):
        self.initialized += 1
        return True

    def shutdown(self):
        self.shutdowns += 1

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 0,
            balance=2000.0,
            equity=1985.0,
            profit=-15.0,
        )

    def positions_get(self):
        return tuple(self.positions)

    def history_deals_get(self, start, end):
        return tuple(self.deals)

    def symbol_info(self, symbol):
        return SimpleNamespace(trade_contract_size=100000.0)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.1, ask=1.1002)

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return self.rates


def provider(fake, symbol="EURUSD"):
    return MT5DemoRiskStateProvider(
        MT5DemoRiskStateConfig(symbol=symbol, timeframe=5),
        mt5_module=fake,
        now=lambda: datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )


def test_reads_authoritative_demo_account_and_positions():
    fake = FakeMT5(
        positions=[
            SimpleNamespace(symbol="EURUSD", volume=0.1, type=FakeMT5.POSITION_TYPE_BUY, price_current=1.1)
        ],
        deals=[
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_IN, position_id=101, profit=0.0, swap=0.0, commission=0.0, fee=0.0, time=1, time_msc=1),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=101, profit=-10.0, swap=0.0, commission=-1.0, fee=0.0, time=2, time_msc=2),
        ],
    )
    state = provider(fake).current_risk_state()

    assert isinstance(state, OperationalState)
    assert state.balance == 2000.0
    assert state.equity == 1985.0
    assert state.unrealized_pnl == -15.0
    assert state.open_positions == 1
    assert state.net_position == 0.1
    assert state.exposure == 11000.0
    assert state.trades_today == 1
    assert state.consecutive_losses == 1
    assert state.realized_pnl == -11.0
    assert state.market_open is True
    assert state.last_processed_candle is None
    assert fake.shutdowns == 1


def test_wrong_account_mode_fails_closed():
    fake = FakeMT5(demo=False)
    with pytest.raises(MT5RiskStateProviderError):
        provider(fake).current_risk_state()
    assert fake.shutdowns == 1


def test_missing_history_fails_closed():
    class BrokenHistory(FakeMT5):
        def history_deals_get(self, start, end):
            return None

    fake = BrokenHistory()
    with pytest.raises(MT5RiskStateProviderError):
        provider(fake).current_risk_state()


def test_invalid_account_value_fails_closed():
    class BrokenAccount(FakeMT5):
        def account_info(self):
            return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, balance=float("nan"), equity=2000.0, profit=0.0)

    with pytest.raises(MT5RiskStateProviderError):
        provider(BrokenAccount()).current_risk_state()


def test_symbol_scope_excludes_other_symbol_from_position_risk():
    fake = FakeMT5(
        positions=[
            SimpleNamespace(symbol="EURUSD", volume=0.1, type=FakeMT5.POSITION_TYPE_BUY, price_current=1.1),
            SimpleNamespace(symbol="GBPUSD", volume=0.5, type=FakeMT5.POSITION_TYPE_SELL, price_current=1.3),
        ]
    )
    state = provider(fake, symbol="EURUSD").current_risk_state()

    assert state.open_positions == 1
    assert state.net_position == 0.1
    assert state.exposure == 11000.0


def test_inout_deal_counts_as_entry_and_exit():
    fake = FakeMT5(
        deals=[
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_INOUT, position_id=303, profit=-5.0, swap=0.0, commission=-1.0, fee=0.0, time=2, time_msc=2),
        ]
    )
    state = provider(fake).current_risk_state()

    assert state.trades_today == 1
    assert state.consecutive_losses == 1
    assert state.realized_pnl == -6.0


def test_partial_exits_count_as_one_logical_loss():
    fake = FakeMT5(
        deals=[
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_IN, position_id=404, profit=0.0, swap=0.0, commission=0.0, fee=0.0, time=1, time_msc=1),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=404, profit=-2.0, swap=0.0, commission=0.0, fee=0.0, time=2, time_msc=2),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=404, profit=-3.0, swap=0.0, commission=0.0, fee=0.0, time=3, time_msc=3),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_IN, position_id=505, profit=0.0, swap=0.0, commission=0.0, fee=0.0, time=4, time_msc=4),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=505, profit=4.0, swap=0.0, commission=0.0, fee=0.0, time=5, time_msc=5),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_IN, position_id=606, profit=0.0, swap=0.0, commission=0.0, fee=0.0, time=6, time_msc=6),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=606, profit=-1.0, swap=0.0, commission=0.0, fee=0.0, time=7, time_msc=7),
        ]
    )
    state = provider(fake).current_risk_state()

    assert state.consecutive_losses == 1
    assert state.realized_pnl == -2.0


def test_reversal_starts_a_new_loss_segment():
    fake = FakeMT5(
        deals=[
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_IN, position_id=707, profit=0.0, swap=0.0, commission=0.0, fee=0.0, time=1, time_msc=1),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_INOUT, position_id=707, profit=-5.0, swap=0.0, commission=0.0, fee=0.0, time=2, time_msc=2),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=707, profit=-4.0, swap=0.0, commission=0.0, fee=0.0, time=3, time_msc=3),
        ]
    )
    state = provider(fake).current_risk_state()

    assert state.consecutive_losses == 2
    assert state.realized_pnl == -9.0


def test_reversal_segment_is_reset_by_a_winning_segment():
    fake = FakeMT5(
        deals=[
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_IN, position_id=808, profit=0.0, swap=0.0, commission=0.0, fee=0.0, time=1, time_msc=1),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_INOUT, position_id=808, profit=-5.0, swap=0.0, commission=0.0, fee=0.0, time=2, time_msc=2),
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, position_id=808, profit=2.0, swap=0.0, commission=0.0, fee=0.0, time=3, time_msc=3),
        ]
    )
    state = provider(fake).current_risk_state()

    assert state.consecutive_losses == 0


def test_missing_position_identity_makes_loss_streak_unknown():
    fake = FakeMT5(
        deals=[
            SimpleNamespace(entry=FakeMT5.DEAL_ENTRY_OUT, profit=-5.0, swap=0.0, commission=0.0, fee=0.0, time=1, time_msc=1),
        ]
    )
    state = provider(fake).current_risk_state()

    assert state.consecutive_losses is None
