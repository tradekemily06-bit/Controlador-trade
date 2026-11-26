import pytest

from data.biquote_provider import BiQuoteProvider
from integration.standalone_market_data_providers import (
    build_configured_market_data_providers,
)


def test_no_market_data_provider_is_enabled_without_explicit_configuration():
    assert build_configured_market_data_providers(None) == {}
    assert build_configured_market_data_providers("") == {}


def test_biquote_provider_is_created_only_when_explicitly_selected():
    providers = build_configured_market_data_providers("biquote")

    assert set(providers) == {"biquote"}
    provider, source = providers["biquote"]
    assert isinstance(provider, BiQuoteProvider)
    assert source == "biquote_public_ohlc"


def test_unknown_provider_configuration_fails_closed():
    with pytest.raises(ValueError, match="unsupported standalone market-data provider"):
        build_configured_market_data_providers("unknown-broker")
