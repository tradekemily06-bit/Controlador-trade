import unittest

from integration.market_data_provider_registry import MarketDataProviderRegistry


class FakeProvider:
    def fetch(self, request):
        return []


class DemoProvider(FakeProvider):
    def get_account_mode(self):
        return "DEMO"


class RealProvider(FakeProvider):
    def get_account_mode(self):
        return "REAL"


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

    def test_selected_provider_exposes_only_verified_demo_or_real_mode(self):
        registry = MarketDataProviderRegistry()
        registry.register("demo", DemoProvider(), "DEMO_FEED")
        self.assertEqual(registry.status()["account_mode"]["mode"], "DEMO")
        registry.register("real", RealProvider(), "REAL_FEED")
        registry.select("real")
        self.assertEqual(registry.status()["account_mode"]["mode"], "REAL")

    def test_provider_without_account_mode_reports_unavailable(self):
        registry = MarketDataProviderRegistry()
        registry.register("default", FakeProvider(), "DEFAULT_FEED")
        self.assertEqual(registry.status()["account_mode"]["status"], "UNAVAILABLE")
        self.assertIsNone(registry.status()["account_mode"]["mode"])

    def test_status_can_skip_active_account_probe_for_readiness_polling(self):
        class ProbeMustNotRun(FakeProvider):
            def get_account_mode(self):
                raise AssertionError("readiness polling must not probe broker terminal")

        registry = MarketDataProviderRegistry()
        registry.register("demo", ProbeMustNotRun(), "DEMO_FEED")
        status = registry.status(probe_account_mode=False)
        self.assertEqual(status["account_mode"]["status"], "NOT_PROBED")
        self.assertFalse(status["account_mode"]["execution_authorized"])

    def test_provider_health_status_reports_live_heartbeat_without_account_probe(self):
        class HealthyRelay(FakeProvider):
            def status(self):
                return {
                    "connected": True,
                    "account_mode": "DEMO",
                    "last_seen": "2026-11-27T00:00:00+00:00",
                    "source_id": "mt5-local",
                    "stored_candles": 42,
                    "secret": "must-not-leak",
                }

        registry = MarketDataProviderRegistry()
        registry.register("mt5_relay", HealthyRelay(), "MT5 local relay DEMO")
        status = registry.status(probe_account_mode=False)
        provider = status["providers"][0]
        self.assertEqual(provider["status"], "CONNECTED")
        self.assertEqual(provider["health"]["account_mode"], "DEMO")
        self.assertEqual(provider["health"]["stored_candles"], 42)
        self.assertNotIn("secret", provider["health"])
        self.assertEqual(status["account_mode"]["status"], "NOT_PROBED")
        self.assertFalse(provider["execution_authorized"])

    def test_provider_health_status_reports_disconnected_heartbeat(self):
        class OfflineRelay(FakeProvider):
            def status(self):
                return {"connected": False, "account_mode": None, "last_seen": None}

        registry = MarketDataProviderRegistry()
        registry.register("mt5_relay", OfflineRelay(), "MT5 local relay DEMO")
        self.assertEqual(registry.status(probe_account_mode=False)["providers"][0]["status"], "DISCONNECTED")

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
