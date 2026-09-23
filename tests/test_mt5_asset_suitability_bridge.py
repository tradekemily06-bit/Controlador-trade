from types import SimpleNamespace

from core.senior_asset_suitability import AssetSuitabilityObservation
from execution.mt5_instrument_universe import MT5InstrumentStatus
from integration.mt5_asset_suitability_bridge import build_asset_suitability_observations


class FakeMT5:
    def __init__(self):
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.ticks = {
            "EURUSD": SimpleNamespace(bid=1.1000, ask=1.1002, time_msc=1000, volume=12, volume_real=0),
            "XAUUSD": SimpleNamespace(bid=2500.0, ask=2500.5, time_msc=2000, volume=8, volume_real=0),
        }

    def initialize(self):
        self.initialize_calls += 1
        return True

    def shutdown(self):
        self.shutdown_calls += 1

    def symbol_info_tick(self, symbol):
        return self.ticks.get(symbol)


def test_bridge_preserves_open_session_and_observable_quote_evidence():
    statuses = (
        MT5InstrumentStatus(
            symbol="EURUSD", asset_class="forex", visible=True,
            tradeable=True, quote_available=True, weekend_capable=False,
            state="OPEN", reason="ok",
        ),
    )
    result = build_asset_suitability_observations(FakeMT5(), statuses)
    observation = result[0]
    assert isinstance(observation, AssetSuitabilityObservation)
    assert observation.session_open is True
    assert observation.quote_fresh is None
    assert observation.quote_timestamped is True
    assert observation.spread_observed == 0.0002
    assert observation.liquidity_observed is True
    assert observation.data_quality_ok is True
    assert observation.domain_expertise_available is False


def test_bridge_does_not_convert_unknown_session_to_open():
    statuses = (
        MT5InstrumentStatus(
            symbol="XAUUSD", asset_class="commodities", visible=True,
            tradeable=True, quote_available=True, weekend_capable=False,
            state="UNKNOWN", reason="calendar unavailable",
        ),
    )
    observation = build_asset_suitability_observations(FakeMT5(), statuses)[0]
    assert observation.session_open is None
