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


def test_ctrader_demo_provider_requires_host_owned_oauth_transport_factory():
    import pytest

    with pytest.raises(RuntimeError, match="OAuth/Open API"):
        build_configured_market_data_providers("ctrader_demo")


def test_ctrader_demo_provider_uses_only_injected_read_only_adapter_factory():
    from integration.ctrader_readonly_market_data_adapter import CTraderReadOnlyMarketDataAdapter

    adapter = CTraderReadOnlyMarketDataAdapter(object(), account_id=123456)
    providers = build_configured_market_data_providers(
        "ctrader_demo",
        ctrader_adapter_factory=lambda: adapter,
    )

    assert list(providers) == ["ctrader_demo"]
    returned, source = providers["ctrader_demo"]
    assert returned is adapter
    assert "DEMO read-only" in source
    assert not hasattr(returned, "place_order")
