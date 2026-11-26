import unittest

from integration.market_data_provider_registry import MarketDataProviderRegistry


class FakeProvider:
    def fetch(self, request):
        return []


class MarketDataProviderRegistryTests(unittest.TestCase):
    def test_register_and_select_multiple_provider_adapters(self):
        registry = MarketDataProviderRegistry()
        registry.register("broker_a", FakeProvider(), "BROKER_A")
        registry.register("broker_b", FakeProvider(), "BROKER_B")
        selected = registry.select("broker_b")
        self.assertEqual(selected.source, "BROKER_B")
        status = registry.status()
        self.assertEqual(status["count"], 2)
        self.assertEqual(status["selected_provider"], "broker_b")
        self.assertFalse(status["providers"][0]["execution_authorized"])

    def test_single_provider_is_selected_by_default(self):
        registry = MarketDataProviderRegistry()
        registry.register("default", FakeProvider(), "DEFAULT_FEED")
        self.assertEqual(registry.selected().provider_id, "default")

    def test_invalid_provider_and_duplicate_are_rejected(self):
        registry = MarketDataProviderRegistry()
        with self.assertRaises(ValueError):
            registry.register("../bad", FakeProvider(), "BAD")
        registry.register("broker_a", FakeProvider(), "BROKER_A")
        with self.assertRaises(ValueError):
            registry.register("broker_a", FakeProvider(), "BROKER_A")
        with self.assertRaises(ValueError):
            registry.select("unknown")


if __name__ == "__main__":
    unittest.main()
