from integration.standalone_runtime import _market_data_provenance_for_provider


def test_verified_mt5_and_ctrader_provider_ids_are_marked_as_real_market_data():
    assert _market_data_provenance_for_provider("mt5_relay") == "REAL_MARKET_DATA"
    assert _market_data_provenance_for_provider("mt5_demo") == "REAL_MARKET_DATA"
    assert _market_data_provenance_for_provider("ctrader_open_api") == "REAL_MARKET_DATA"


def test_unknown_or_untrusted_provider_ids_are_not_marked_as_real_market_data():
    assert _market_data_provenance_for_provider("ctrader") is None
    assert _market_data_provenance_for_provider("tradingview_webhook") is None
    assert _market_data_provenance_for_provider("unknown") is None
    assert _market_data_provenance_for_provider(None) is None
