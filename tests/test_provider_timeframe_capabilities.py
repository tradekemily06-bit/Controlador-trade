from data.biquote_provider import BiQuoteProvider
from data.timeframes import list_supported_timeframes
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter


def test_biquote_declares_fixed_intervals_derived_from_closed_base_candles():
    provider = BiQuoteProvider()
    assert all(provider.supports_timeframe(item) for item in list_supported_timeframes())
    assert provider.supports_timeframe("M10")
    assert not provider.supports_timeframe("MN1")
    assert not provider.supports_timeframe("30s")


def test_mt5_declares_native_intervals_without_initializing_terminal():
    provider = ICMarketsMT5DemoMarketDataAdapter(mt5_module=object())
    assert provider.supports_timeframe("M1")
    assert provider.supports_timeframe("M5")
    assert provider.supports_timeframe("M10")
    assert provider.supports_timeframe("H1")
    assert provider.supports_timeframe("D1")
    assert provider.supports_timeframe("W1")
    assert not provider.supports_timeframe("M7")
    assert not provider.supports_timeframe("MN1")
    assert not provider.supports_timeframe("30s")
    assert provider._mt5 is not None

