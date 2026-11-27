from __future__ import annotations

import unittest

from core.unified_intelligence import ApplicationArea, UnifiedIntelligence
from integration.unified_ecosystem_application import UnifiedEcosystemApplication


class UnifiedIntelligenceTests(unittest.TestCase):
    def test_all_seven_areas_share_one_intelligence(self):
        intelligence = UnifiedIntelligence()
        self.assertEqual(len(intelligence.areas), 7)
        self.assertEqual(
            {area.area.value for area in intelligence.areas},
            {area.value for area in ApplicationArea},
        )
        self.assertEqual(intelligence.architecture_status()["architecture"], "ONE_SHARED_INTELLIGENCE")

    def test_senior_knowledge_is_internal_not_an_eighth_area(self):
        intelligence = UnifiedIntelligence()
        status = intelligence.architecture_status()
        self.assertEqual(status["internal_knowledge"]["senior_experience_baseline_years"], 45)
        self.assertTrue(status["internal_knowledge"]["experience_open_ended"])
        self.assertNotIn("senior_experience", {area.area.value for area in intelligence.areas})

    def test_all_routes_are_non_executing(self):
        intelligence = UnifiedIntelligence()
        for area in ApplicationArea:
            route = intelligence.route(area=area, task="consultar")
            self.assertFalse(route.execution_authorized)
            self.assertIn("shared_intelligence", route.selected_capabilities)

    def test_unconnected_area_is_not_falsely_reported_as_connected(self):
        app = UnifiedEcosystemApplication()
        result = app.handle(area=ApplicationArea.TAX_RESERVE, task="consultar fila Brasil")
        self.assertEqual(result["status"], "NOT_CONNECTED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(app.architecture()["all_area_handlers_connected"])

    def test_handler_cannot_submit_orders_or_claim_execution_authority(self):
        app = UnifiedEcosystemApplication()
        app.register_handler(
            ApplicationArea.ECOSYSTEM_ASSISTANT,
            lambda task, context, intelligence: {"order_submitted": True},
        )
        with self.assertRaises(ValueError):
            app.handle(area=ApplicationArea.ECOSYSTEM_ASSISTANT, task="executar")

    def test_unknown_area_is_rejected(self):
        with self.assertRaises(ValueError):
            UnifiedIntelligence().route(area="other", task="consultar")


if __name__ == "__main__":
    unittest.main()
