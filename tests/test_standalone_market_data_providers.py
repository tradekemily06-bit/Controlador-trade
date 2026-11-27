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



def test_multiple_market_data_providers_can_be_registered_together(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_RUNTIME_DIR", str(tmp_path))
    providers = build_configured_market_data_providers("biquote,mt5_relay")

    assert set(providers) == {"biquote", "mt5_relay"}
    assert providers["biquote"][1] == "biquote_public_ohlc"
    assert providers["mt5_relay"][1] == "MT5 local relay DEMO read-only"


def test_duplicate_market_data_provider_is_rejected():
    with pytest.raises(ValueError, match="duplicate market-data provider"):
        build_configured_market_data_providers("biquote,biquote")


def test_provider_list_keeps_legacy_single_provider_configuration():
    providers = build_configured_market_data_providers("biquote")
    assert set(providers) == {"biquote"}
