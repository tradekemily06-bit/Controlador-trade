from integration.standalone_market_data_providers import build_configured_market_data_providers
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter


def test_mt5_demo_provider_is_explicitly_opt_in():
    assert build_configured_market_data_providers(None) == {}
    assert build_configured_market_data_providers("") == {}


def test_mt5_demo_provider_factory_returns_read_only_adapter():
    providers = build_configured_market_data_providers("mt5_demo")

    assert list(providers) == ["mt5_demo"]
    adapter, source = providers["mt5_demo"]
    assert isinstance(adapter, ICMarketsMT5DemoMarketDataAdapter)
    assert "read-only" in source
    assert not hasattr(adapter, "place_order")


def test_mt5_demo_provider_accepts_explicit_alias():
    providers = build_configured_market_data_providers("icmarkets_mt5_demo")
    assert list(providers) == ["mt5_demo"]


def test_mt5_relay_provider_factory_uses_persistent_store(monkeypatch, tmp_path):
    from integration.mt5_relay_store import MT5RelayStore

    monkeypatch.setenv("CONTROLADOR_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("CONTROLADOR_MT5_RELAY_SOURCE_ID", "local-demo")
    providers = build_configured_market_data_providers("mt5_relay")

    provider, source = providers["mt5_relay"]
    assert isinstance(provider, MT5RelayStore)
    assert "read-only" in source
    assert not hasattr(provider, "place_order")
