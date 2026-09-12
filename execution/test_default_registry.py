from execution.default_registry import IC_MARKETS_MT5_DEMO, build_demo_registry
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter


def test_default_demo_registry_registers_ic_markets_without_connecting():
    class UnusedMT5:
        def initialize(self):
            raise AssertionError("registry construction must not initialize MT5")

    registry = build_demo_registry(mt5_module=UnusedMT5())

    assert registry.names() == (IC_MARKETS_MT5_DEMO,)
    assert isinstance(registry.get(IC_MARKETS_MT5_DEMO), ICMarketsMT5DemoAdapter)


def test_default_demo_registry_can_override_symbol():
    registry = build_demo_registry(symbol="EURUSD")
    adapter = registry.get(IC_MARKETS_MT5_DEMO)

    assert adapter.config.symbol == "EURUSD"
