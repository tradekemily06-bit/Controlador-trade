from __future__ import annotations

import unittest

from core.unified_intelligence import ApplicationArea
from integration.standalone_application_factory import build_standalone_application


class FakeService:
    senior_context = None

    def system_status(self):
        return {"state": "READY"}

    def risk_status(self):
        return {"allowed": False}

    def operational_observability(self):
        return {"execution": {"allowed": False}}

    def notification_summary(self):
        return {"items": []}

    def learning_summary(self):
        return {"execution_allowed": False}

    def statistics(self):
        return {"total": 0}

    def memory_view(self, limit=50):
        return []

    def connections(self):
        return {"broker": "NOT_CONNECTED"}

    def saas_status(self):
        return {"identity": "NOT_CONFIGURED"}


class StandaloneApplicationFactoryTests(unittest.TestCase):
    def test_existing_read_only_services_are_wired_to_shared_intelligence(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        architecture = app.architecture()
        self.assertEqual(architecture["architecture"], "ONE_SHARED_INTELLIGENCE")
        self.assertEqual(architecture["area_handler_status"]["command_cabin"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["analysis"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["study"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["memory"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["control_center"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["tax_reserve"], "NOT_CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["ecosystem_assistant"], "NOT_CONNECTED")

    def test_command_cabin_is_read_only(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(area=ApplicationArea.COMMAND_CABIN, task="status")
        self.assertEqual(result["status"], "CONNECTED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["result"]["execution_authorized"])

    def test_analysis_requires_validated_market_context(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(area=ApplicationArea.ANALYSIS, task="analisar")
        self.assertEqual(result["result"]["status"], "DATA_PROVIDER_NOT_CONFIGURED")
        self.assertFalse(result["execution_authorized"])

    def test_missing_fiscal_owner_rejected(self):
        from finance.fiscal_reserve import FiscalReserve
        with self.assertRaises(ValueError):
            build_standalone_application(
                ecosystem_service=FakeService(),
                fiscal_reserve=FiscalReserve(),
            )


if __name__ == "__main__":
    unittest.main()
